import csv
import datetime
import calendar
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.models import User
from django.db.models import Q
from Student.models import Student, StudentCourse, Project, Exam, ExamMarks, Attendance, Faculty, StudentBatch, DailyWorkReport, Batch
from Management.models import Admin


def get_current_admin(request):
    admin_id = request.session.get("admin_id")
    if admin_id:
        return (
            User.objects.filter(id=admin_id, is_active=True)
            .filter(Q(is_superuser=True) | Q(is_staff=True))
            .first()
        )
    return None


def get_admin_profile(user):
    """
    Returns the associated Management.Admin record for the given auth.User.
    Creates or updates it if needed so Admin and User stay seamlessly synced.
    """
    admin_prof = None
    if user.email:
        admin_prof = Admin.objects.filter(email__iexact=user.email).first()
    if not admin_prof:
        full_name = f"{user.first_name} {user.last_name}".strip() or user.username
        admin_prof, _ = Admin.objects.get_or_create(
            email=user.email or f"{user.username}@creative.com",
            defaults={
                "name": full_name,
                "password": user.password,
            }
        )
    return admin_prof

def get_user_faculty_courses(user):
    """
    Returns list of course names taught by the given user if they are a faculty member.
    Inspects both Management.Admin profile and Student.Faculty record.
    """
    if not user:
        return []
    admin_prof = get_admin_profile(user)
    courses = []
    if admin_prof and admin_prof.faculty_courses:
        for c in admin_prof.faculty_courses.split(","):
            c = c.strip()
            if c and c not in courses:
                courses.append(c)
    fac = Faculty.objects.filter(
        Q(admin_account=admin_prof) | Q(email__iexact=user.email),
        is_active=True
    ).first()
    if fac and fac.courses:
        for c in fac.courses_list:
            c = c.strip()
            if c and c not in courses:
                courses.append(c)
    return courses


def filter_students_for_faculty(queryset, user):
    """
    If user is superuser (Admin), returns the full student queryset.
    If user is only Faculty (non-superuser), restricts the queryset to only students
    enrolled in courses taught by this faculty, or assigned to this faculty member.
    """
    if not user or user.is_superuser:
        return queryset
    faculty_courses = get_user_faculty_courses(user)
    admin_prof = get_admin_profile(user)
    fac = Faculty.objects.filter(
        Q(admin_account=admin_prof) | Q(email__iexact=user.email),
        is_active=True
    ).first()

    if not faculty_courses and not fac:
        return queryset.none()

    q_filter = Q()
    for c in faculty_courses:
        q_filter |= Q(course__icontains=c) | Q(enrolled_courses__course_name__icontains=c)
        clean_name = c
        for prefix in ["Master In ", "Master in ", "Advance ", "Diploma In ", "Diploma in "]:
            if clean_name.startswith(prefix):
                clean_name = clean_name[len(prefix):].strip()
                break
        if clean_name and clean_name != c and len(clean_name) >= 3:
            q_filter |= Q(course__icontains=clean_name) | Q(enrolled_courses__course_name__icontains=clean_name)

    if fac:
        q_filter |= Q(faculty_member=fac) | Q(assigned_batch__faculty=fac) | Q(assigned_batches__faculty=fac)

    return queryset.filter(q_filter).distinct()


def filter_batches_for_faculty(batches_qs, user):
    """
    If user is superuser (Admin), returns full batches queryset.
    If user is only Faculty (non-superuser), restricts batches to those taught by this
    faculty member, or matching their course, or containing their students.
    """
    if not user or user.is_superuser:
        return batches_qs
    faculty_courses = get_user_faculty_courses(user)
    admin_prof = get_admin_profile(user)
    fac = Faculty.objects.filter(
        Q(admin_account=admin_prof) | Q(email__iexact=user.email),
        is_active=True
    ).first()
    faculty_students = filter_students_for_faculty(Student.objects.all(), user)

    b_q = Q(students__in=faculty_students)
    if fac:
        b_q |= Q(faculty=fac)
    for c in faculty_courses:
        b_q |= Q(course__icontains=c)
        clean = c
        for p in ["Master In ", "Master in ", "Advance ", "Diploma In ", "Diploma in "]:
            if clean.startswith(p):
                clean = clean[len(p):].strip()
                break
        if clean and clean != c and len(clean) >= 3:
            b_q |= Q(course__icontains=clean)

    return batches_qs.filter(b_q).distinct()



# --- ADMIN AUTH & PROFILE VIEWS ---


def admin_login_view(request):
    user = get_current_admin(request)
    if user:
        return redirect("admin_dashboard")

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        admin_user = (
            User.objects.filter(email__iexact=email, is_active=True)
            .filter(Q(is_superuser=True) | Q(is_staff=True))
            .first()
            or User.objects.filter(username__iexact=email, is_active=True)
            .filter(Q(is_superuser=True) | Q(is_staff=True))
            .first()
        )

        if admin_user:
            if check_password(password, admin_user.password):
                request.session["admin_id"] = admin_user.id
                request.session["admin_name"] = admin_user.username
                request.session["admin_email"] = admin_user.email
                messages.success(request, f"Welcome back, {admin_user.username}!")
                return redirect("admin_dashboard")
            else:
                messages.error(request, "Invalid password!")
        else:
            messages.error(request, "Invalid admin credentials!")

    return render(request, "management/login.html")


def admin_logout_view(request):
    if "admin_id" in request.session:
        del request.session["admin_id"]
    request.session.flush()
    messages.success(request, "Successfully logged out!")
    return redirect("admin_login")


def admin_profile_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    admin_prof = get_admin_profile(user)
    students_count = Student.objects.count()
    faculties_count = Faculty.objects.count()
    projects_count = Project.objects.count()
    approved_projects_count = Project.objects.filter(status="Approved").count()
    submitted_projects_count = Project.objects.filter(status="Submitted").count()
    exams_count = Exam.objects.count()

    today = datetime.date.today()
    today_work_reports_count = DailyWorkReport.objects.filter(date=today).count()
    today_attendance_count = Attendance.objects.filter(date=today).count()

    faculty_courses_list = []
    if admin_prof and admin_prof.faculty_courses:
        faculty_courses_list = [c.strip() for c in admin_prof.faculty_courses.split(",") if c.strip()]

    context = {
        "user": user,
        "admin_user": user,
        "admin_prof": admin_prof,
        "total_students": students_count,
        "total_faculties": faculties_count,
        "total_projects": projects_count,
        "approved_projects_count": approved_projects_count,
        "submitted_projects_count": submitted_projects_count,
        "total_exams": exams_count,
        "today_work_reports_count": today_work_reports_count,
        "today_attendance_count": today_attendance_count,
        "faculty_courses_list": faculty_courses_list,
    }
    return render(request, "management/profile.html", context)


def admin_change_password_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    admin_prof = get_admin_profile(user)
    context = {
        "user": user,
        "admin_user": user,
        "admin_prof": admin_prof,
    }

    if request.method == "POST":
        current_password = request.POST.get("current_password")
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")

        if not (current_password and new_password and confirm_password):
            messages.error(request, "Please fill in all password fields!")
            return render(request, "management/change_password.html", context)

        if not check_password(current_password, user.password):
            messages.error(request, "Current password is incorrect!")
            return render(request, "management/change_password.html", context)

        if len(new_password) < 6:
            messages.error(request, "New password must be at least 6 characters long!")
            return render(request, "management/change_password.html", context)

        if new_password != confirm_password:
            messages.error(request, "New password and Confirm password do not match!")
            return render(request, "management/change_password.html", context)

        user.password = make_password(new_password)
        user.save()
        if admin_prof:
            admin_prof.password = user.password
            admin_prof.save()

        messages.success(request, "Your administrative password has been changed successfully!")
        return redirect("admin_profile")

    return render(request, "management/change_password.html", context)


# --- ADMIN DASHBOARD & STUDENTS ---


def format_slot_short(slot):
    clean = slot.lower().replace("am", "").replace("pm", "").strip()
    parts = clean.split("to")
    if len(parts) == 2:
        p1 = parts[0].strip().replace(":00", "").lstrip("0") or "0"
        p2 = parts[1].strip().replace(":00", "").lstrip("0") or "0"
        return f"{p1} to {p2}"
    return slot


def admin_dashboard_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    students = Student.objects.all().order_by("-created_at")
    students = filter_students_for_faculty(students, user)
    projects = Project.objects.all().order_by("-submitted_at")
    exams = Exam.objects.all().order_by("-exam_date")
    if not user.is_superuser:
        projects = projects.filter(student__in=students)
        exams = exams.filter(students__in=students).distinct()

    admins = User.objects.filter(Q(is_superuser=True) | Q(is_staff=True), is_active=True)

    pending_projects_count = projects.filter(status="Submitted").count()
    approved_projects_count = projects.filter(status="Approved").count()

    today = datetime.date.today()
    today_records = Attendance.objects.filter(date=today)
    if not user.is_superuser:
        today_records = today_records.filter(student__in=students)
    today_present = today_records.filter(status="Present").count()
    today_absent = today_records.filter(status="Absent").count()
    today_late = today_records.filter(status="Late").count()
    today_marked = today_records.count()
    today_attendance_pct = (
        round(((today_present + today_late) / today_marked) * 100, 1)
        if today_marked > 0
        else 0
    )

    # Build Batches Schedule Matrix (Faculty vs Time Slots)
    class_time_choices = [c[0] for c in Student.CLASS_TIME_CHOICES]
    time_slots = [{"full": s, "short": format_slot_short(s)} for s in class_time_choices]
    faculties = Faculty.objects.filter(is_active=True).order_by("department", "name")
    active_batches = list(
        Batch.objects.filter(is_active=True)
        .select_related("faculty")
        .prefetch_related("students")
    )

    faculty_batch_matrix = []
    for f in faculties:
        row_slots = []
        for slot in class_time_choices:
            slot_batches = [
                b for b in active_batches
                if b.faculty_id == f.id and b.time_slot.strip().lower() == slot.strip().lower()
            ]
            row_slots.append({
                "slot": slot,
                "batches": slot_batches,
                "has_batches": len(slot_batches) > 0,
            })
        total_b = sum(len(s["batches"]) for s in row_slots)
        total_s = sum(sum(b.student_count for b in s["batches"]) for s in row_slots)
        faculty_batch_matrix.append({
            "faculty": f,
            "faculty_name": f.name,
            "faculty_dept": f.department,
            "slots": row_slots,
            "total_batches": total_b,
            "total_students": total_s,
        })

    # Include unassigned faculty batches if any exist
    unassigned_faculty_batches = [b for b in active_batches if not b.faculty_id]
    if unassigned_faculty_batches:
        unassigned_slots = []
        for slot in class_time_choices:
            slot_batches = [
                b for b in unassigned_faculty_batches
                if b.time_slot.strip().lower() == slot.strip().lower()
            ]
            unassigned_slots.append({
                "slot": slot,
                "batches": slot_batches,
                "has_batches": len(slot_batches) > 0,
            })
        total_b = sum(len(s["batches"]) for s in unassigned_slots)
        total_s = sum(sum(b.student_count for b in s["batches"]) for s in unassigned_slots)
        faculty_batch_matrix.append({
            "faculty": None,
            "faculty_name": "Unassigned Instructor",
            "faculty_dept": "Open Batches",
            "slots": unassigned_slots,
            "total_batches": total_b,
            "total_students": total_s,
        })

    context = {
        "user": user,
        "total_students": students.count(),
        "total_projects": projects.count(),
        "pending_projects_count": pending_projects_count,
        "approved_projects_count": approved_projects_count,
        "total_exams": exams.count(),
        "total_admins": admins.count(),
        "recent_students": students[:5],
        "recent_projects": projects.select_related("student")[:5],
        "recent_exams": exams[:4],
        "today_marked": today_marked,
        "today_present": today_present,
        "today_absent": today_absent,
        "today_late": today_late,
        "today_attendance_pct": today_attendance_pct,
        "time_slots": time_slots,
        "faculty_batch_matrix": faculty_batch_matrix,
        "total_active_batches": len(active_batches),
    }
    return render(request, "management/dashboard.html", context)


def student_register_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")
    if not user.is_superuser:
        messages.error(request, "Permission denied: Faculty members cannot create students.")
        return redirect("admin_student_list")

    class_time_choices = [c[0] for c in Student.CLASS_TIME_CHOICES]
    course_categories = Student.COURSE_CATEGORIES
    faculties = Faculty.objects.filter(is_active=True).order_by("department", "name")
    all_students = Student.objects.all().order_by("name")
    all_staff = Faculty.objects.filter(is_active=True).order_by("name")

    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        password = request.POST.get("password")
        selected_courses = request.POST.getlist("courses")
        if not selected_courses:
            course_str = request.POST.get("course", "").strip()
            if course_str:
                selected_courses = [c.strip() for c in course_str.split(",") if c.strip()]

        selected_batches = request.POST.getlist("class_times")
        if not selected_batches:
            selected_batches = request.POST.getlist("class_time")
        if not selected_batches:
            raw_batch = request.POST.get("class_time", "").strip()
            if raw_batch:
                selected_batches = [b.strip() for b in raw_batch.split(",") if b.strip()]

        class_time_str = ", ".join(selected_batches)
        phone = request.POST.get("phone", "")

        reference = request.POST.get("reference", "").strip()
        if reference == "Internet":
            reference_detail = request.POST.get("reference_internet", "").strip()
        elif reference == "Student":
            reference_detail = request.POST.get("reference_student", "").strip()
        elif reference == "Staff":
            reference_detail = request.POST.get("reference_staff", "").strip()
        elif reference == "Seminar":
            reference_detail = request.POST.get("reference_seminar", "").strip()
        elif reference == "Other":
            reference_detail = request.POST.get("reference_other", "").strip()
        else:
            reference_detail = request.POST.get("reference_detail", "").strip()

        if not (name and email and password and selected_courses):
            messages.error(request, "Please fill in all required fields including at least one course!")
            return render(
                request,
                "management/student_register.html",
                {
                    "user": user,
                    "class_time_choices": class_time_choices,
                    "course_categories": course_categories,
                    "all_students": all_students,
                    "all_staff": all_staff,
                },
            )

        if Student.objects.filter(email=email).exists():
            messages.error(request, "Email already registered!")
            return render(
                request,
                "management/student_register.html",
                {
                    "user": user,
                    "class_time_choices": class_time_choices,
                    "course_categories": course_categories,
                    "all_students": all_students,
                    "all_staff": all_staff,
                },
            )

        student = Student.objects.create(
            name=name,
            email=email,
            password=make_password(password),
            course=", ".join(selected_courses),
            class_time=class_time_str,
            phone=phone,
            reference=reference,
            reference_detail=reference_detail,
        )

        # Automatically assign student to matching active batches based on selected timings,
        # inheriting instructor/faculty assignment directly from the batch.
        primary_batch = None
        for b in selected_batches:
            StudentBatch.objects.get_or_create(student=student, batch_time=b)
            matching_batch = Batch.objects.filter(time_slot__iexact=b.strip(), is_active=True).first()
            if matching_batch:
                matching_batch.students.add(student)
                if not primary_batch:
                    primary_batch = matching_batch

        if primary_batch:
            student.assigned_batch = primary_batch
            if primary_batch.faculty:
                student.faculty_member = primary_batch.faculty
                student.faculty = primary_batch.faculty.name
            student.save(update_fields=['assigned_batch', 'faculty_member', 'faculty'])

        for c in selected_courses:
            StudentCourse.objects.get_or_create(
                student=student, 
                course_name=c,
                defaults={
                    "faculty": student.faculty or "",
                    "faculty_member": student.faculty_member
                }
            )

        batch_count_msg = f"{len(selected_batches)} batch schedule(s)" if selected_batches else "flexible schedule"
        fac_msg = f" (assigned to batch instructor: {student.faculty})" if student.faculty else ""
        messages.success(request, f"Student {name} registered successfully with {len(selected_courses)} course(s), {batch_count_msg}{fac_msg}!")
        return redirect("admin_student_list")

    return render(
        request,
        "management/student_register.html",
        {
            "user": user,
            "class_time_choices": class_time_choices,
            "course_categories": course_categories,
            "faculties": faculties,
            "all_students": all_students,
            "all_staff": all_staff,
        },
    )


def student_list_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    students = Student.objects.all().order_by("-created_at")
    is_only_faculty = not user.is_superuser
    faculty_courses = get_user_faculty_courses(user) if is_only_faculty else []
    if is_only_faculty:
        students = filter_students_for_faculty(students, user)
    base_students = students
    q = request.GET.get("q", "").strip()
    course_filter = request.GET.get("course", "").strip()
    class_time_filter = request.GET.get("class_time", "").strip()

    if q:
        students = students.filter(
            Q(name__icontains=q)
            | Q(email__icontains=q)
            | Q(course__icontains=q)
            | Q(enrolled_courses__course_name__icontains=q)
            | Q(class_time__icontains=q)
            | Q(phone__icontains=q)
        ).distinct()

    if course_filter:
        students = students.filter(
            Q(course__icontains=course_filter) | Q(enrolled_courses__course_name=course_filter)
        ).distinct()

    if class_time_filter:
        students = students.filter(
            Q(class_time__icontains=class_time_filter) | Q(enrolled_batches__batch_time=class_time_filter)
        ).distinct()

    batch_faculty_filter = request.GET.get("batch_faculty", "").strip() or request.GET.get("faculty", "").strip()
    if batch_faculty_filter:
        fac_q = (
            Q(assigned_batch__faculty__name__icontains=batch_faculty_filter)
            | Q(assigned_batches__faculty__name__icontains=batch_faculty_filter)
            | Q(faculty__icontains=batch_faculty_filter)
            | Q(faculty_member__name__icontains=batch_faculty_filter)
            | Q(enrolled_courses__faculty__icontains=batch_faculty_filter)
            | Q(enrolled_courses__faculty_member__name__icontains=batch_faculty_filter)
        )
        if batch_faculty_filter.isdigit():
            fac_q |= Q(assigned_batch__faculty__id=int(batch_faculty_filter)) | Q(assigned_batches__faculty__id=int(batch_faculty_filter))
        first_token = batch_faculty_filter.split()[0] if " " in batch_faculty_filter else ""
        if first_token and len(first_token) >= 3:
            fac_q |= (
                Q(assigned_batch__faculty__name__icontains=first_token)
                | Q(assigned_batches__faculty__name__icontains=first_token)
                | Q(faculty__icontains=first_token)
            )
        students = students.filter(fac_q).distinct()

    # Automatically sync expired leave status
    Student.sync_expired_leaves()

    status_filter = request.GET.get("status", "").strip()
    if status_filter == "leave" or status_filter == "On Leave":
        students = students.filter(Q(status="On Leave") | Q(is_on_leave=True))
    elif status_filter == "active":
        students = students.filter(is_on_leave=False)
    elif status_filter in [c[0] for c in Student.STUDENT_STATUS_CHOICES]:
        students = students.filter(status=status_filter)

    batch_param = request.GET.get("batch_id", "").strip() or request.GET.get("batch_status", "").strip() or request.GET.get("batch", "").strip()
    batch_filter = ""
    batch_id_filter = ""

    if batch_param.isdigit():
        batch_id_filter = batch_param
    elif batch_param.startswith("batch_"):
        batch_id_filter = batch_param.replace("batch_", "")
    elif batch_param in ["unassigned", "assigned"]:
        batch_filter = batch_param

    selected_batch_obj = None
    if batch_id_filter and batch_id_filter.isdigit():
        selected_batch_obj = Batch.objects.filter(id=int(batch_id_filter)).first()
        students = students.filter(Q(assigned_batch__id=int(batch_id_filter)) | Q(assigned_batches__id=int(batch_id_filter))).distinct()
    elif batch_filter == "unassigned":
        students = students.filter(assigned_batch__isnull=True, assigned_batches__isnull=True)
    elif batch_filter == "assigned":
        students = students.filter(Q(assigned_batch__isnull=False) | Q(assigned_batches__isnull=False)).distinct()

    course_categories = Student.COURSE_CATEGORIES
    if is_only_faculty and faculty_courses:
        fc_lower = [fc.lower() for fc in faculty_courses]
        filtered_cats = {}
        for cat, c_list in Student.COURSE_CATEGORIES.items():
            matched = [c for c in c_list if any(c.lower() in fc or fc in c.lower() for fc in fc_lower)]
            if matched:
                filtered_cats[cat] = matched
        if filtered_cats:
            course_categories = filtered_cats

    class_time_choices = [c[0] for c in Student.CLASS_TIME_CHOICES]
    faculties = Faculty.objects.filter(is_active=True).order_by("department", "name")

    context = {
        "user": user,
        "students": students,
        "query": q,
        "course_filter": course_filter,
        "class_time_filter": class_time_filter,
        "batch_faculty_filter": batch_faculty_filter,
        "faculty_filter": batch_faculty_filter,
        "course_categories": course_categories,
        "class_time_choices": class_time_choices,
        "faculties": faculties,
        "status_filter": status_filter,
        "batch_filter": batch_filter,
        "batch_id_filter": batch_id_filter,
        "selected_batch_obj": selected_batch_obj,
        "all_batches": Batch.objects.filter(is_active=True).select_related('faculty').order_by('time_slot', 'name'),
        "unassigned_batch_count": base_students.filter(assigned_batch__isnull=True, assigned_batches__isnull=True).count(),
        "on_leave_count": base_students.filter(is_on_leave=True).count(),
        "active_students_count": base_students.filter(is_on_leave=False).count(),
        "total_students_count": base_students.count(),
        "status_choices": [c[0] for c in Student.STUDENT_STATUS_CHOICES],
        "is_only_faculty": is_only_faculty,
        "faculty_courses": faculty_courses,
    }

    return render(request, "management/student_list.html", context)


def student_detail_view(request, student_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    student = Student.objects.filter(id=student_id).first()
    if not student:
        messages.error(request, "Student not found.")
        return redirect("admin_student_list")

    if not user.is_superuser:
        faculty_courses = get_user_faculty_courses(user)
        fc_lower = [fc.lower() for fc in faculty_courses]
        student_courses = [c.lower() for c in student.courses_list]
        student_raw = (student.course or "").lower()
        has_course = any(
            any(fc in sc or sc in fc for sc in student_courses) or (fc in student_raw)
            for fc in fc_lower
        )
        if not has_course:
            messages.error(request, "Permission denied: You do not have permission to view students outside your assigned courses.")
            return redirect("admin_student_list")

    projects = Project.objects.filter(student=student).prefetch_related("files", "links").order_by("-submitted_at")
    marks_records = ExamMarks.objects.filter(student=student).order_by("-exam__exam_date")

    total_obtained = sum(m.marks_obtained for m in marks_records if m.marks_obtained is not None)
    total_possible = sum(m.exam.total_marks for m in marks_records if m.marks_obtained is not None)
    percentage = (
        round((float(total_obtained) / float(total_possible) * 100), 2)
        if total_possible > 0
        else 0
    )

    recent_attendance = student.attendance_records.all()[:15]
    attendance_stats = student.attendance_stats

    context = {
        "user": user,
        "student": student,
        "projects": projects,
        "marks_records": marks_records,
        "total_obtained": total_obtained,
        "total_possible": total_possible,
        "percentage": percentage,
        "recent_attendance": recent_attendance,
        "attendance_stats": attendance_stats,
    }
    return render(request, "management/student_detail.html", context)


def student_edit_view(request, student_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")
    if not user.is_superuser:
        messages.error(request, "Permission denied: Faculty members cannot edit student information.")
        return redirect("admin_student_list")

    student = Student.objects.filter(id=student_id).first()
    if not student:
        messages.error(request, "Student not found.")
        return redirect("admin_student_list")

    class_time_choices = [c[0] for c in Student.CLASS_TIME_CHOICES]
    course_categories = Student.COURSE_CATEGORIES
    faculties = Faculty.objects.filter(is_active=True).order_by("department", "name")
    all_students = Student.objects.exclude(id=student.id).order_by("name")
    all_staff = Faculty.objects.filter(is_active=True).order_by("name")
    next_url = request.GET.get("next") or request.POST.get("next") or "detail"

    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        selected_courses = request.POST.getlist("courses")
        if not selected_courses:
            course_str = request.POST.get("course", "").strip()
            if course_str:
                selected_courses = [c.strip() for c in course_str.split(",") if c.strip()]

        selected_batches = request.POST.getlist("class_times")
        if not selected_batches:
            selected_batches = request.POST.getlist("class_time")
        if not selected_batches:
            raw_batch = request.POST.get("class_time", "").strip()
            if raw_batch:
                selected_batches = [b.strip() for b in raw_batch.split(",") if b.strip()]

        if not selected_courses:
            messages.error(request, "Student must be enrolled in at least one course!")
            return render(
                request,
                "management/student_edit.html",
                {
                    "user": user,
                    "student": student,
                    "class_time_choices": class_time_choices,
                    "course_categories": course_categories,
                    "faculties": faculties,
                    "next_url": next_url,
                },
            )

        if email != student.email and Student.objects.filter(email=email).exists():
            messages.error(request, "Email already in use by another student!")
            return render(
                request,
                "management/student_edit.html",
                {
                    "user": user,
                    "student": student,
                    "class_time_choices": class_time_choices,
                    "course_categories": course_categories,
                    "faculties": faculties,
                    "next_url": next_url,
                },
            )

        if password:
            student.password = make_password(password)

        reference = request.POST.get("reference", "").strip()
        if reference == "Internet":
            reference_detail = request.POST.get("reference_internet", "").strip()
        elif reference == "Student":
            reference_detail = request.POST.get("reference_student", "").strip()
        elif reference == "Staff":
            reference_detail = request.POST.get("reference_staff", "").strip()
        elif reference == "Seminar":
            reference_detail = request.POST.get("reference_seminar", "").strip()
        elif reference == "Other":
            reference_detail = request.POST.get("reference_other", "").strip()
        else:
            reference_detail = request.POST.get("reference_detail", "").strip()

        student.name = request.POST.get("name")
        student.email = email
        student.course = ", ".join(selected_courses)
        student.class_time = ", ".join(selected_batches)
        student.phone = request.POST.get("phone")
        student.reference = reference
        student.reference_detail = reference_detail

        # Sync StudentBatch & Batch assignment, automatically inheriting instructor from batch
        for b in student.assigned_batches.exclude(time_slot__in=selected_batches):
            b.students.remove(student)

        primary_batch = None
        StudentBatch.objects.filter(student=student).exclude(batch_time__in=selected_batches).delete()
        for b in selected_batches:
            StudentBatch.objects.get_or_create(student=student, batch_time=b)
            matching_batch = Batch.objects.filter(time_slot__iexact=b.strip(), is_active=True).first()
            if matching_batch:
                matching_batch.students.add(student)
                if not primary_batch:
                    primary_batch = matching_batch

        if primary_batch:
            student.assigned_batch = primary_batch
            if primary_batch.faculty:
                student.faculty_member = primary_batch.faculty
                student.faculty = primary_batch.faculty.name
            else:
                student.faculty_member = None
                student.faculty = ""
        elif not selected_batches:
            student.assigned_batch = None
            student.faculty_member = None
            student.faculty = ""
        elif student.assigned_batch and student.assigned_batch.faculty:
            student.faculty_member = student.assigned_batch.faculty
            student.faculty = student.assigned_batch.faculty.name

        student.save()

        # Sync StudentCourse table
        StudentCourse.objects.filter(student=student).exclude(course_name__in=selected_courses).delete()
        for c in selected_courses:
            sc, _ = StudentCourse.objects.get_or_create(student=student, course_name=c)
            sc.faculty = student.faculty
            sc.faculty_member = student.faculty_member
            sc.save()

        messages.success(request, f"Student {student.name} updated successfully!")
        if next_url == "list":
            return redirect("admin_student_list")
        return redirect("admin_student_detail", student_id=student.id)

    return render(
        request,
        "management/student_edit.html",
        {
            "user": user,
            "student": student,
            "class_time_choices": class_time_choices,
            "course_categories": course_categories,
            "faculties": faculties,
            "all_students": all_students,
            "all_staff": all_staff,
            "next_url": next_url,
        },
    )


def student_delete_view(request, student_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")
    if not user.is_superuser:
        messages.error(request, "Permission denied: Faculty members cannot delete students.")
        return redirect("admin_student_list")

    student = Student.objects.filter(id=student_id).first()
    if not student:
        messages.error(request, "Student not found.")
        return redirect("admin_student_list")

    name = student.name
    student.delete()
    messages.success(request, f"Student '{name}' and all associated records deleted.")
    return redirect("admin_student_list")


def student_toggle_leave_view(request, student_id):
    user = get_current_admin(request)
    if not user:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"status": "error", "message": "Unauthorized"}, status=401)
        return redirect("admin_login")

    student = Student.objects.filter(id=student_id).first()
    if not student:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"status": "error", "message": "Student not found."}, status=404)
        messages.error(request, "Student not found.")
        return redirect("admin_student_list")

    next_url = request.POST.get("next") or request.GET.get("next") or reverse("admin_student_list")

    if request.method == "POST":
        action = request.POST.get("action", "").strip()
        if action == "mark_active" or action == "resume":
            today = datetime.date.today()
            Attendance.objects.filter(
                student=student,
                date__gte=today,
                status="Leave",
                remarks__icontains="On Leave"
            ).delete()
            student.is_on_leave = False
            student.status = "Running"
            student.leave_reason = ""
            student.leave_start_date = None
            student.leave_end_date = None
            student.save()
            messages.success(request, f"Student '{student.name}' is now marked as Active (Classes Resumed).")
        else:
            leave_reason = request.POST.get("leave_reason", "").strip()
            student.leave_reason = leave_reason

            start_date_str = request.POST.get("leave_start_date", "").strip()
            end_date_str = request.POST.get("leave_end_date", "").strip()

            if not start_date_str or not end_date_str:
                messages.error(request, "Both Start Date and End Date are mandatory.")
                return redirect(next_url)

            try:
                start_date = datetime.date.fromisoformat(start_date_str)
            except ValueError:
                messages.error(request, "Invalid Start Date format.")
                return redirect(next_url)

            try:
                end_date = datetime.date.fromisoformat(end_date_str)
            except ValueError:
                messages.error(request, "Invalid End Date format.")
                return redirect(next_url)

            if end_date < start_date:
                messages.error(request, "Leave End Date cannot be earlier than Start Date.")
                return redirect(next_url)

            student.leave_start_date = start_date
            student.leave_end_date = end_date

            today = datetime.date.today()
            if student.leave_end_date < today:
                student.status = "Running"
                student.is_on_leave = False
                student.leave_reason = ""
                student.leave_start_date = None
                student.leave_end_date = None
            elif student.leave_start_date > today:
                student.status = "Running"
                student.is_on_leave = False
            else:
                student.status = "On Leave"
                student.is_on_leave = True

            student.save()

            # Automatically sync attendance records as Leave for the full leave date range
            day_count = (end_date - start_date).days
            if day_count <= 90:
                slot = student.class_time or (student.batches_list[0] if student.batches_list else "")
                for i in range(day_count + 1):
                    cur_date = start_date + datetime.timedelta(days=i)
                    Attendance.objects.update_or_create(
                        student=student,
                        date=cur_date,
                        defaults={
                            "status": "Leave",
                            "time_slot": slot,
                            "remarks": f"On Leave: {leave_reason}" if leave_reason else "On Leave",
                            "marked_by": f"Admin ({user.username})",
                        }
                    )

            if end_date < today:
                messages.info(request, f"Leave dates for '{student.name}' have already ended. Attendance was recorded, and student remains Active.")
            elif start_date > today:
                messages.success(request, f"Leave scheduled for '{student.name}' from {start_date} to {end_date}.")
            else:
                messages.success(request, f"Student '{student.name}' has been marked On Leave until {end_date}.")

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({
                "status": "success",
                "is_on_leave": student.is_on_leave,
                "status_display": student.status_display,
                "student_id": student.id,
                "student_name": student.name,
                "leave_reason": student.leave_reason,
                "leave_start_date": student.leave_start_date.isoformat() if student.leave_start_date else "",
                "leave_end_date": student.leave_end_date.isoformat() if student.leave_end_date else "",
            })
        return redirect(next_url)

    # GET request support
    action = request.GET.get("action", "").strip()
    if action == "toggle":
        if student.is_on_leave:
            student.is_on_leave = False
            student.status = "Running"
            student.leave_reason = ""
            student.leave_start_date = None
            student.leave_end_date = None
            student.save()
            messages.success(request, f"Student '{student.name}' is now marked as Active.")
        else:
            student.is_on_leave = True
            student.status = "On Leave"
            student.leave_start_date = datetime.date.today()
            student.save()
            messages.success(request, f"Student '{student.name}' is marked On Leave.")
        return redirect(next_url)

    return redirect(next_url)


def admin_student_status_update_view(request, student_id):
    user = get_current_admin(request)
    if not user:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"status": "error", "message": "Unauthorized"}, status=401)
        return redirect("admin_login")

    student = Student.objects.filter(id=student_id).first()
    if not student:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"status": "error", "message": "Student not found."}, status=404)
        messages.error(request, "Student not found.")
        return redirect("admin_student_list")

    next_url = request.POST.get("next") or request.GET.get("next") or request.META.get("HTTP_REFERER") or reverse("admin_student_list")

    if request.method == "POST":
        new_status = request.POST.get("status", "").strip()
        valid_statuses = [c[0] for c in Student.STUDENT_STATUS_CHOICES]
        if new_status not in valid_statuses:
            messages.error(request, f"Invalid status '{new_status}' selected.")
            return redirect(next_url)

        today = datetime.date.today()

        if new_status == "On Leave":
            leave_reason = request.POST.get("leave_reason", "").strip()
            start_date_str = request.POST.get("leave_start_date", "").strip()
            end_date_str = request.POST.get("leave_end_date", "").strip()

            if not start_date_str or not end_date_str:
                messages.error(request, "Both Start Date and End Date are mandatory when marking student On Leave.")
                return redirect(next_url)

            try:
                start_date = datetime.date.fromisoformat(start_date_str)
            except ValueError:
                messages.error(request, "Invalid Start Date format.")
                return redirect(next_url)

            try:
                end_date = datetime.date.fromisoformat(end_date_str)
            except ValueError:
                messages.error(request, "Invalid End Date format.")
                return redirect(next_url)

            if end_date < start_date:
                messages.error(request, "Leave End Date cannot be earlier than Start Date.")
                return redirect(next_url)

            student.leave_reason = leave_reason
            student.leave_start_date = start_date
            student.leave_end_date = end_date

            # Automatically sync attendance records as Leave for the full date range
            day_count = (end_date - start_date).days
            if day_count <= 90:
                slot = student.class_time or (student.batches_list[0] if student.batches_list else "")
                for i in range(day_count + 1):
                    cur_date = start_date + datetime.timedelta(days=i)
                    Attendance.objects.update_or_create(
                        student=student,
                        date=cur_date,
                        defaults={
                            "status": "Leave",
                            "time_slot": slot,
                            "remarks": f"On Leave: {leave_reason}" if leave_reason else "On Leave",
                            "marked_by": f"Admin ({user.username})",
                        }
                    )

            if end_date < today:
                student.status = "Running"
                student.is_on_leave = False
                student.leave_reason = ""
                student.leave_start_date = None
                student.leave_end_date = None
                student.save()
                messages.info(request, f"Leave dates for '{student.name}' have already ended. Attendance was recorded, and student remains Running.")
            elif start_date > today:
                student.status = "Running"
                student.is_on_leave = False
                student.save()
                messages.success(request, f"Leave scheduled for '{student.name}' from {start_date} to {end_date}.")
            else:
                student.status = "On Leave"
                student.is_on_leave = True
                student.save()
                messages.success(request, f"Student '{student.name}' status updated to On Leave until {end_date}.")

        else:
            # If changing from On Leave to another status, clear future Leave attendance records
            if student.is_on_leave or student.status == "On Leave":
                Attendance.objects.filter(
                    student=student,
                    date__gte=today,
                    status="Leave",
                    remarks__icontains="On Leave"
                ).delete()

            student.status = new_status
            student.is_on_leave = False
            student.leave_reason = ""
            student.leave_start_date = None
            student.leave_end_date = None
            student.save()

            messages.success(request, f"Student '{student.name}' status updated to {new_status} successfully.")

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({
                "status": "success",
                "student_id": student.id,
                "student_name": student.name,
                "student_status": student.status,
                "status_display": student.status_display,
                "is_on_leave": student.is_on_leave,
            })

        return redirect(next_url)

    return redirect(next_url)


# --- STUDENT PROJECTS VIEWS ---


def admin_projects_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    student_id = request.GET.get("student_id")

    projects = Project.objects.select_related("student").prefetch_related("files", "links").order_by("-submitted_at")
    if not user.is_superuser:
        faculty_students = filter_students_for_faculty(Student.objects.all(), user)
        projects = projects.filter(student__in=faculty_students)
        students = faculty_students.order_by("name")
    else:
        students = Student.objects.all().order_by("name")

    total_projects_count = projects.count()

    if student_id:
        projects = projects.filter(student_id=student_id)

    context = {
        "user": user,
        "projects": projects,
        "students": students,
        "student_filter": student_id,
        "total_projects_count": total_projects_count,
    }
    return render(request, "management/projects_list.html", context)


def admin_project_detail_view(request, project_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    project = Project.objects.filter(id=project_id).select_related("student").prefetch_related("files", "links").first()
    if not project:
        messages.error(request, "Project not found.")
        return redirect("admin_projects")

    if not user.is_superuser:
        faculty_students = filter_students_for_faculty(Student.objects.all(), user)
        if not faculty_students.filter(id=project.student_id).exists():
            messages.error(request, "Permission denied: You do not have access to projects for this student.")
            return redirect("admin_projects")

    context = {
        "user": user,
        "project": project,
    }
    return render(request, "management/project_detail.html", context)


def project_status_update_view(request, project_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    if request.method == "POST":
        project = Project.objects.filter(id=project_id).first()
        if not project:
            messages.error(request, "Project not found.")
            return redirect("admin_projects")

        new_status = request.POST.get("status")
        project.status = new_status
        project.save()
        messages.success(
            request, f"Status of project '{project.title}' updated to {new_status}."
        )

    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url == "detail":
        return redirect("admin_project_detail", project_id=project_id)
    return redirect("admin_projects")


# --- EXAMS & MARKS WORKFLOW VIEWS (BATCH-CENTRIC) ---
EXCLUDED_EXAM_STUDENT_STATUSES = ['Dropped', 'On Leave', 'Suspend']

def get_eligible_exam_students_for_batches(batches):
    """
    Returns eligible students for given batches, excluding students whose
    status is 'Dropped', 'On Leave', or 'Suspend', or who are currently on leave.
    Checks both direct assigned_batch and ManyToMany assigned_batches.
    """
    if not batches:
        return []
    return list(
        Student.objects.filter(
            Q(assigned_batch__in=batches) | Q(assigned_batches__in=batches)
        ).exclude(
            status__in=EXCLUDED_EXAM_STUDENT_STATUSES
        ).exclude(
            is_on_leave=True
        ).distinct()
    )



def exam_list_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    q = request.GET.get("q", "").strip()
    batch_param = request.GET.get("batch_id", "").strip() or request.GET.get("batch", "").strip()
    status_filter = request.GET.get("status", "").strip()

    all_batches_qs = Batch.objects.filter(is_active=True).select_related("faculty").prefetch_related("students").order_by("time_slot", "name")
    if not user.is_superuser:
        all_batches_qs = filter_batches_for_faculty(all_batches_qs, user)
    all_batches = list(all_batches_qs)

    batch_id_filter = ""
    selected_batch_obj = None
    if batch_param.isdigit():
        batch_id_filter = batch_param
        selected_batch_obj = next((b for b in all_batches if b.id == int(batch_param)), None)
        if not selected_batch_obj:
            selected_batch_obj = Batch.objects.filter(id=int(batch_param)).first()
    elif batch_param.startswith("batch_"):
        batch_id_filter = batch_param.replace("batch_", "")
        selected_batch_obj = next((b for b in all_batches if str(b.id) == batch_id_filter), None)

    exams_qs = (
        Exam.objects.prefetch_related("students", "marks_records", "batches")
        .all()
        .order_by("-exam_date", "-id")
    )
    if not user.is_superuser:
        faculty_students = filter_students_for_faculty(Student.objects.all(), user)
        exams_qs = exams_qs.filter(Q(students__in=faculty_students) | Q(batches__in=all_batches)).distinct()

    if q:
        exams_qs = exams_qs.filter(
            Q(title__icontains=q)
            | Q(subject__icontains=q)
            | Q(batches__name__icontains=q)
            | Q(batches__course__icontains=q)
        ).distinct()

    if selected_batch_obj:
        exams_qs = exams_qs.filter(
            Q(batches=selected_batch_obj)
            | Q(students__assigned_batch=selected_batch_obj)
            | Q(students__assigned_batches=selected_batch_obj)
        ).distinct()
    elif batch_param:
        exams_qs = exams_qs.filter(
            Q(batches__time_slot__icontains=batch_param)
            | Q(batches__name__icontains=batch_param)
            | Q(students__class_time__icontains=batch_param)
            | Q(students__assigned_batches__time_slot__icontains=batch_param)
        ).distinct()

    all_filtered_exams = list(exams_qs)
    total_exams_count = len(all_filtered_exams)

    # Build individual exam cards with stats
    exam_cards = []
    faculty_students = filter_students_for_faculty(Student.objects.all(), user) if not user.is_superuser else None
    for exam in all_filtered_exams:
        if not user.is_superuser:
            exam_students = exam.students.filter(id__in=faculty_students)
            total_students = exam_students.count()
            marks_records = exam.marks_records.filter(student__in=faculty_students)
        else:
            total_students = exam.students.count()
            marks_records = exam.marks_records.all()
        graded_count = sum(1 for m in marks_records if m.marks_obtained is not None and not m.is_absent)
        absent_count = sum(1 for m in marks_records if m.is_absent)
        pending_count = total_students - (graded_count + absent_count)

        graded_marks = [float(m.marks_obtained) for m in marks_records if m.marks_obtained is not None and not m.is_absent]
        avg_score = round(sum(graded_marks) / len(graded_marks), 1) if graded_marks else None

        card_data = {
            "exam": exam,
            "total_students": total_students,
            "graded_count": graded_count,
            "absent_count": absent_count,
            "pending_count": pending_count,
            "avg_score": avg_score,
            "is_complete": total_students > 0 and pending_count == 0,
        }

        if status_filter == "completed" and not card_data["is_complete"]:
            continue
        elif status_filter == "pending" and (pending_count == 0 or total_students == 0):
            continue
        elif status_filter == "empty" and total_students > 0:
            continue

        exam_cards.append(card_data)

    # -----------------------------------------------------------------
    # Build Batch Groups for the "By Batches" tab
    # -----------------------------------------------------------------
    if selected_batch_obj:
        target_batches = [selected_batch_obj]
    elif batch_param:
        target_batches = [
            b for b in all_batches
            if batch_param.lower() in b.time_slot.lower() or batch_param.lower() in b.name.lower()
        ]
    else:
        target_batches = all_batches

    batch_groups = []
    covered_exam_ids = set()

    for b in target_batches:
        b_student_ids = set(b.active_exam_students.values_list("id", flat=True))

        b_exams = []
        for card in exam_cards:
            exam = card["exam"]
            is_linked = exam.batches.filter(id=b.id).exists()
            has_students = any(s.id in b_student_ids for s in exam.students.all())
            if is_linked or has_students:
                b_exams.append(card)
                covered_exam_ids.add(exam.id)

        total_evaluations = sum(c["total_students"] for c in b_exams)
        total_graded = sum(c["graded_count"] for c in b_exams)
        total_pending = sum(c["pending_count"] for c in b_exams)

        batch_groups.append({
            "batch": b,
            "exams": b_exams,
            "total_exams": len(b_exams),
            "total_students": len(b_student_ids),
            "total_evaluations": total_evaluations,
            "total_graded": total_graded,
            "total_pending": total_pending,
            "has_exams": len(b_exams) > 0,
        })

    # Group any assessments not associated with active named batches
    unassigned_exams = [c for c in exam_cards if c["exam"].id not in covered_exam_ids]
    unassigned_group = None
    if unassigned_exams:
        unassigned_group = {
            "title": "General & Cross-Batch Assessments",
            "exams": unassigned_exams,
            "total_exams": len(unassigned_exams),
            "total_students": sum(c["total_students"] for c in unassigned_exams),
            "total_graded": sum(c["graded_count"] for c in unassigned_exams),
            "total_pending": sum(c["pending_count"] for c in unassigned_exams),
        }

    class_time_choices = [c[0] for c in Student.CLASS_TIME_CHOICES]

    context = {
        "user": user,
        "exam_cards": exam_cards,
        "batch_groups": batch_groups,
        "unassigned_group": unassigned_group,
        "all_batches": all_batches,
        "batch_filter": batch_param,
        "batch_id_filter": batch_id_filter,
        "selected_batch_obj": selected_batch_obj,
        "class_time_choices": class_time_choices,
        "status_filter": status_filter,
        "query": q,
        "total_exams_count": total_exams_count,
    }
    return render(request, "management/exam_list.html", context)


def exam_create_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    all_batches_qs = Batch.objects.filter(is_active=True).select_related("faculty").prefetch_related("students").order_by("time_slot", "name")
    if not user.is_superuser:
        all_batches_qs = filter_batches_for_faculty(all_batches_qs, user)
    all_batches = list(all_batches_qs)

    preselected_batch_id = request.GET.get("batch_id", "").strip()
    preselected_batch = None
    if preselected_batch_id.isdigit():
        preselected_batch = next((b for b in all_batches if b.id == int(preselected_batch_id)), None)

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        subject = request.POST.get("subject", "").strip()
        exam_date = request.POST.get("exam_date")
        exam_time = request.POST.get("exam_time", "").strip()
        total_marks = request.POST.get("total_marks", "100")
        batch_ids = request.POST.getlist("batch_ids")

        if not (title and subject and exam_date and total_marks):
            messages.error(request, "Please fill in all required exam fields!")
            return render(
                request,
                "management/exam_form.html",
                {
                    "user": user,
                    "all_batches": all_batches,
                    "preselected_batch": preselected_batch,
                    "is_edit": False,
                },
            )

        if not batch_ids:
            messages.error(request, "Please select at least one batch for this exam!")
            return render(
                request,
                "management/exam_form.html",
                {
                    "user": user,
                    "all_batches": all_batches,
                    "preselected_batch": preselected_batch,
                    "is_edit": False,
                },
            )

        exam = Exam.objects.create(
            title=title,
            subject=subject,
            exam_date=exam_date,
            exam_time=exam_time,
            total_marks=float(total_marks),
        )

        sel_batches = list(Batch.objects.filter(id__in=batch_ids))
        exam.batches.set(sel_batches)

        # Automatically enroll eligible students from selected batches (exclude Dropped, On Leave, Suspend)
        unique_students = get_eligible_exam_students_for_batches(sel_batches)

        if unique_students:
            exam.students.set(unique_students)
            for s in unique_students:
                ExamMarks.objects.get_or_create(exam=exam, student=s)

        batch_names_str = ", ".join(b.name for b in sel_batches)
        messages.success(
            request,
            f"Exam '{title}' scheduled for batch(es) [{batch_names_str}] ({len(unique_students)} students enrolled)!"
        )
        return redirect("admin_exam_detail", exam_id=exam.id)

    return render(
        request,
        "management/exam_form.html",
        {
            "user": user,
            "all_batches": all_batches,
            "preselected_batch": preselected_batch,
            "is_edit": False,
        },
    )

def exam_detail_view(request, exam_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    exam = Exam.objects.filter(id=exam_id).first()
    if not exam:
        messages.error(request, "Exam not found.")
        return redirect("admin_exam_list")

    # Automatically purge/remove any students whose status is Dropped, On Leave, or Suspend
    excluded_students = exam.students.filter(
        Q(status__in=EXCLUDED_EXAM_STUDENT_STATUSES) | Q(is_on_leave=True)
    )
    if excluded_students.exists():
        exam.students.remove(*excluded_students)
        ExamMarks.objects.filter(exam=exam, student__in=excluded_students).delete()

    for student in exam.students.exclude(status__in=EXCLUDED_EXAM_STUDENT_STATUSES).exclude(is_on_leave=True):
        ExamMarks.objects.get_or_create(exam=exam, student=student)

    marks_records = (
        ExamMarks.objects.filter(exam=exam)
        .exclude(student__status__in=EXCLUDED_EXAM_STUDENT_STATUSES)
        .exclude(student__is_on_leave=True)
        .select_related("student", "student__assigned_batch")
        .prefetch_related("student__assigned_batches")
        .order_by("student__name")
    )
    if not user.is_superuser:
        faculty_students = filter_students_for_faculty(Student.objects.all(), user)
        marks_records = marks_records.filter(student__in=faculty_students)

    graded_records = [m for m in marks_records if m.marks_obtained is not None and not m.is_absent]
    absent_records = [m for m in marks_records if m.is_absent]
    graded_count = len(graded_records)
    absent_count = len(absent_records)
    total_students = marks_records.count()
    pending_count = total_students - graded_count - absent_count

    avg_marks = 0
    if graded_count > 0:
        avg_marks = round(sum(float(m.marks_obtained) for m in graded_records) / graded_count, 2)

    all_batches_qs = Batch.objects.filter(is_active=True).select_related("faculty").prefetch_related("students").order_by("time_slot", "name")
    if not user.is_superuser:
        all_batches_qs = filter_batches_for_faculty(all_batches_qs, user)
    all_batches = list(all_batches_qs)

    batch_marks_groups = []
    accounted_student_ids = set()

    for b in all_batches:
        b_records = [
            m for m in marks_records
            if m.student.assigned_batch_id == b.id or b in m.student.assigned_batches.all()
        ]
        if b_records or exam.batches.filter(id=b.id).exists():
            accounted_student_ids.update(m.student_id for m in b_records)
            b_graded = [m for m in b_records if m.marks_obtained is not None and not m.is_absent]
            b_absent = [m for m in b_records if m.is_absent]
            b_avg = (
                round(sum(float(m.marks_obtained) for m in b_graded) / len(b_graded), 1)
                if b_graded else 0
            )
            batch_marks_groups.append({
                "batch": b,
                "records": b_records,
                "total_students": len(b_records),
                "graded_count": len(b_graded),
                "absent_count": len(b_absent),
                "pending_count": len(b_records) - len(b_graded) - len(b_absent),
                "avg_marks": b_avg,
                "is_complete": len(b_records) > 0 and (len(b_graded) + len(b_absent)) == len(b_records),
            })

    unassigned_records = [m for m in marks_records if m.student_id not in accounted_student_ids]
    unassigned_batch_group = None
    if unassigned_records:
        u_graded = [m for m in unassigned_records if m.marks_obtained is not None and not m.is_absent]
        u_absent = [m for m in unassigned_records if m.is_absent]
        u_avg = (
            round(sum(float(m.marks_obtained) for m in u_graded) / len(u_graded), 1)
            if u_graded else 0
        )
        unassigned_batch_group = {
            "title": "Flexible / Other Students",
            "records": unassigned_records,
            "total_students": len(unassigned_records),
            "graded_count": len(u_graded),
            "absent_count": len(u_absent),
            "pending_count": len(unassigned_records) - len(u_graded) - len(u_absent),
            "avg_marks": u_avg,
            "is_complete": len(unassigned_records) > 0 and (len(u_graded) + len(u_absent)) == len(unassigned_records),
        }

    existing_exam_batch_ids = set(exam.batches.values_list("id", flat=True))
    available_batches = [
        {"batch": b, "unenrolled_count": b.active_exam_students_count}
        for b in all_batches
        if b.id not in existing_exam_batch_ids
    ]
    available_students = []

    context = {
        "user": user,
        "exam": exam,
        "marks_records": marks_records,
        "batch_marks_groups": batch_marks_groups,
        "unassigned_batch_group": unassigned_batch_group,
        "available_batches": available_batches,
        "all_batches": all_batches,
        "total_students": total_students,
        "graded_count": graded_count,
        "absent_count": absent_count,
        "pending_count": pending_count,
        "avg_marks": avg_marks,
        "available_students": available_students,
    }
    return render(request, "management/exam_detail.html", context)


def exam_marks_save_view(request, exam_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    exam = Exam.objects.filter(id=exam_id).first()
    if not exam:
        messages.error(request, "Exam not found.")
        return redirect("admin_exam_list")

    if request.method == "POST":
        action = request.POST.get("action", "save")

        if action == "save_all":
            saved_count = 0
            for key, val in request.POST.items():
                if key.startswith("marks_"):
                    s_id = key.replace("marks_", "")
                    if s_id.isdigit():
                        mark_record = ExamMarks.objects.filter(exam=exam, student_id=int(s_id)).first()
                        if mark_record:
                            if val.strip() != "":
                                try:
                                    f_val = float(val)
                                    if 0 <= f_val <= float(exam.total_marks):
                                        mark_record.is_absent = False
                                        mark_record.marks_obtained = f_val
                                        mark_record.save()
                                        saved_count += 1
                                except ValueError:
                                    pass
                            else:
                                if mark_record.marks_obtained is not None and not mark_record.is_absent:
                                    mark_record.marks_obtained = None
                                    mark_record.grade = None
                                    mark_record.save()
            messages.success(request, f"Evaluations saved for {saved_count} student{{'s' if saved_count != 1 else ''}}.")
            return redirect("admin_exam_detail", exam_id=exam.id)

        student_id = request.POST.get("student_id")
        marks_val = request.POST.get("marks_obtained")

        student = Student.objects.filter(id=student_id).first()
        if not student:
            messages.error(request, "Student not found.")
            return redirect("admin_exam_detail", exam_id=exam.id)

        mark_record, _ = ExamMarks.objects.get_or_create(exam=exam, student=student)

        if action == "mark_absent":
            mark_record.is_absent = True
            mark_record.marks_obtained = None
            mark_record.save()
            messages.warning(request, f"{student.name} marked as Absent.")
        elif action == "clear_absent":
            mark_record.is_absent = False
            mark_record.marks_obtained = None
            mark_record.grade = None
            mark_record.save()
            messages.info(request, f"{student.name} marked as Present. Ready for marks entry.")
        else:
            if marks_val is not None and marks_val.strip() != "":
                try:
                    marks_float = float(marks_val)
                    if marks_float < 0 or marks_float > float(exam.total_marks):
                        messages.error(request, f"Marks must be between 0 and {exam.total_marks}!")
                        return redirect("admin_exam_detail", exam_id=exam.id)
                    mark_record.is_absent = False
                    mark_record.marks_obtained = marks_float
                    mark_record.save()
                    messages.success(request, f"Marks for {student.name} recorded ({marks_float}/{exam.total_marks} - Grade {mark_record.grade})!")
                except ValueError:
                    messages.error(request, "Invalid marks entered.")
            else:
                mark_record.is_absent = False
                mark_record.marks_obtained = None
                mark_record.grade = None
                mark_record.save()
                messages.success(request, f"Marks cleared for {student.name}.")

    return redirect("admin_exam_detail", exam_id=exam.id)


def exam_add_student_view(request, exam_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    exam = Exam.objects.filter(id=exam_id).first()
    if not exam:
        messages.error(request, "Exam not found.")
        return redirect("admin_exam_list")

    if request.method == "POST":
        student_id = request.POST.get("student_id")
        student = Student.objects.filter(id=student_id).first()
        if student:
            exam.students.add(student)
            ExamMarks.objects.get_or_create(exam=exam, student=student)
            messages.success(request, f"Enrolled {student.name} into {exam.title}.")

    return redirect("admin_exam_detail", exam_id=exam.id)


def exam_add_batch_view(request, exam_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    exam = Exam.objects.filter(id=exam_id).first()
    if not exam:
        messages.error(request, "Exam not found.")
        return redirect("admin_exam_list")

    if request.method == "POST":
        batch_id = request.POST.get("batch_id")
        batch = Batch.objects.filter(id=batch_id).first()
        if batch:
            exam.batches.add(batch)
            eligible_students = get_eligible_exam_students_for_batches([batch])
            for s in eligible_students:
                exam.students.add(s)
                ExamMarks.objects.get_or_create(exam=exam, student=s)
            messages.success(request, f"Enrolled batch '{batch.name}' ({len(eligible_students)} students) into {exam.title}!")
        else:
            messages.error(request, "Batch not found.")

    return redirect("admin_exam_detail", exam_id=exam.id)


def exam_remove_student_view(request, exam_id, student_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    exam = Exam.objects.filter(id=exam_id).first()
    student = Student.objects.filter(id=student_id).first()
    if exam and student:
        exam.students.remove(student)
        ExamMarks.objects.filter(exam=exam, student=student).delete()
        messages.success(request, f"Removed {student.name} from exam.")

    return redirect("admin_exam_detail", exam_id=exam.id)


def exam_edit_view(request, exam_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    exam = Exam.objects.filter(id=exam_id).first()
    if not exam:
        messages.error(request, "Exam not found.")
        return redirect("admin_exam_list")

    all_batches_qs = Batch.objects.filter(is_active=True).select_related("faculty").prefetch_related("students").order_by("time_slot", "name")
    if not user.is_superuser:
        all_batches_qs = filter_batches_for_faculty(all_batches_qs, user)
    all_batches = list(all_batches_qs)
    assigned_batch_ids = set(exam.batches.values_list("id", flat=True))

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        subject = request.POST.get("subject", "").strip()
        exam_date = request.POST.get("exam_date")
        exam_time = request.POST.get("exam_time", "").strip()
        total_marks = request.POST.get("total_marks", "100")
        batch_ids = request.POST.getlist("batch_ids")

        if not (title and subject and exam_date and total_marks):
            messages.error(request, "Please fill in all required fields!")
            return render(
                request,
                "management/exam_form.html",
                {
                    "user": user,
                    "exam": exam,
                    "all_batches": all_batches,
                    "assigned_batch_ids": assigned_batch_ids,
                    "is_edit": True,
                },
            )

        if not batch_ids:
            messages.error(request, "Please select at least one batch for this exam!")
            return render(
                request,
                "management/exam_form.html",
                {
                    "user": user,
                    "exam": exam,
                    "all_batches": all_batches,
                    "assigned_batch_ids": assigned_batch_ids,
                    "is_edit": True,
                },
            )

        exam.title = title
        exam.subject = subject
        exam.exam_date = exam_date
        exam.exam_time = exam_time
        exam.total_marks = float(total_marks)
        exam.save()

        sel_batches = list(Batch.objects.filter(id__in=batch_ids))
        exam.batches.set(sel_batches)

        # Automatically update enrolled students from selected batches (exclude Dropped, On Leave, Suspend)
        unique_students = get_eligible_exam_students_for_batches(sel_batches)
        exam.students.set(unique_students)

        for s in unique_students:
            ExamMarks.objects.get_or_create(exam=exam, student=s)

        # Remove marks records for any students who are not in eligible unique_students
        # (purges any students who became Dropped, On Leave, Suspend or whose batch was deselected)
        ExamMarks.objects.filter(exam=exam).exclude(student__in=unique_students).delete()

        for m in exam.marks_records.filter(marks_obtained__isnull=False):
            m.save()

        batch_names_str = ", ".join(b.name for b in sel_batches)
        messages.success(
            request,
            f"Exam '{exam.title}' updated for batch(es) [{batch_names_str}] ({len(unique_students)} students enrolled)!"
        )
        return redirect("admin_exam_detail", exam_id=exam.id)

    return render(
        request,
        "management/exam_form.html",
        {
            "user": user,
            "exam": exam,
            "all_batches": all_batches,
            "assigned_batch_ids": assigned_batch_ids,
            "is_edit": True,
        },
    )

def exam_delete_view(request, exam_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    exam = Exam.objects.filter(id=exam_id).first()
    if not exam:
        messages.error(request, "Exam not found.")
        return redirect("admin_exam_list")

    title = exam.title
    exam.delete()
    messages.success(request, f"Exam '{title}' and all associated marks deleted.")
    return redirect("admin_exam_list")


def admin_faculty_courses_update_view(request, admin_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    target_user = User.objects.filter(id=admin_id).first()
    if not target_user:
        messages.error(request, "User account not found.")
        return redirect("admin_list")

    # Only superusers or the faculty member themselves can update/request courses
    if not (user.is_superuser or user.id == target_user.id):
        messages.error(request, "Permission denied: Only Administrators can update faculty teaching courses.")
        return redirect("admin_list")

    admin_prof = get_admin_profile(target_user)
    fac = Faculty.objects.filter(admin_account=admin_prof, is_active=True).first()

    if request.method == "POST":
        selected_courses = request.POST.getlist("courses")
        courses_str = ", ".join(c.strip() for c in selected_courses if c.strip())
        count = len([c for c in selected_courses if c.strip()])

        if user.is_superuser:
            # Administrator is directly updating -> immediate effect
            admin_prof.faculty_courses = courses_str
            admin_prof.pending_faculty_courses = ""
            admin_prof.course_request_status = "Approved"
            admin_prof.is_faculty = True
            admin_prof.save()

            if fac:
                fac.courses = courses_str
                fac.pending_courses = ""
                fac.course_request_status = "Approved"
                fac.save()
            else:
                full_name = f"{target_user.first_name} {target_user.last_name}".strip() or target_user.username
                Faculty.objects.create(
                    admin_account=admin_prof,
                    name=full_name,
                    email=target_user.email,
                    phone=admin_prof.phone or "",
                    is_admin=target_user.is_superuser,
                    is_active=True,
                    courses=courses_str,
                    password=admin_prof.password or "",
                )

            messages.success(request, f"Faculty profile updated: {count} course(s) assigned to '{target_user.username}'.")
        else:
            # Faculty member requested course update -> REQUIRES ADMIN APPROVAL
            from django.utils import timezone
            admin_prof.pending_faculty_courses = courses_str
            admin_prof.course_request_status = "Pending"
            admin_prof.course_request_date = timezone.now()
            admin_prof.save()

            if fac:
                fac.pending_courses = courses_str
                fac.course_request_status = "Pending"
                fac.course_request_date = timezone.now()
                fac.save()

            messages.info(
                request,
                f"Course update request submitted ({count} course(s) selected). Administrator approval is required before changes take effect."
            )

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or reverse("admin_list")
    return redirect(next_url)


def admin_faculty_course_request_approve_view(request, admin_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")
    if not user.is_superuser:
        messages.error(request, "Permission denied: Only Administrators can approve course updates.")
        return redirect("admin_list")

    target_user = User.objects.filter(id=admin_id).first()
    if not target_user:
        messages.error(request, "User account not found.")
        return redirect("admin_list")

    admin_prof = get_admin_profile(target_user)
    if not admin_prof or not admin_prof.pending_faculty_courses:
        messages.warning(request, f"No pending course update request found for '{target_user.username}'.")
        return redirect("admin_list")

    approved_courses = admin_prof.pending_faculty_courses
    admin_prof.faculty_courses = approved_courses
    admin_prof.pending_faculty_courses = ""
    admin_prof.course_request_status = "Approved"
    admin_prof.is_faculty = True
    admin_prof.save()

    fac = Faculty.objects.filter(admin_account=admin_prof, is_active=True).first()
    if fac:
        fac.courses = approved_courses
        fac.pending_courses = ""
        fac.course_request_status = "Approved"
        fac.save()
    else:
        full_name = f"{target_user.first_name} {target_user.last_name}".strip() or target_user.username
        Faculty.objects.create(
            admin_account=admin_prof,
            name=full_name,
            email=target_user.email,
            is_admin=target_user.is_superuser,
            is_active=True,
            courses=approved_courses,
            password=admin_prof.password or "",
        )

    messages.success(request, f"Course update request approved for '{target_user.username}'. Assigned: {approved_courses}")
    next_url = request.META.get("HTTP_REFERER") or reverse("admin_list")
    return redirect(next_url)


def admin_faculty_course_request_reject_view(request, admin_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")
    if not user.is_superuser:
        messages.error(request, "Permission denied: Only Administrators can reject course updates.")
        return redirect("admin_list")

    target_user = User.objects.filter(id=admin_id).first()
    if not target_user:
        messages.error(request, "User account not found.")
        return redirect("admin_list")

    admin_prof = get_admin_profile(target_user)
    if admin_prof:
        admin_prof.pending_faculty_courses = ""
        admin_prof.course_request_status = "Rejected"
        admin_prof.save()

    fac = Faculty.objects.filter(admin_account=admin_prof, is_active=True).first()
    if fac:
        fac.pending_courses = ""
        fac.course_request_status = "Rejected"
        fac.save()

    messages.info(request, f"Course update request for '{target_user.username}' was rejected.")
    next_url = request.META.get("HTTP_REFERER") or reverse("admin_list")
    return redirect(next_url)


# --- ADMIN MANAGEMENT OVERVIEW & CRUD ---


def sync_faculty_and_admin_users():
    """
    Ensures every active Faculty record and Management.Admin record has a corresponding
    auth.User account (with is_staff=True), so that all faculty instructors and staff
    seamlessly appear in the Administration directory, have full profile editing capabilities,
    and can log into the portal.
    """
    for fac in Faculty.objects.filter(is_active=True):
        email = fac.email or f"faculty_{fac.id}@creative.com"
        adm = fac.admin_account
        if not adm:
            adm = Admin.objects.filter(email__iexact=email).first()
            if not adm:
                adm = Admin.objects.create(
                    name=fac.name,
                    email=email,
                    phone=fac.phone or "",
                    is_faculty=True,
                    faculty_courses=fac.courses or "",
                    faculty_department=fac.department or "",
                    faculty_specialization=fac.specialization or "",
                )
            fac.admin_account = adm
            fac.save(update_fields=["admin_account"])
        else:
            if not adm.is_faculty:
                adm.is_faculty = True
                adm.save(update_fields=["is_faculty"])
            if fac.courses and not adm.faculty_courses:
                adm.faculty_courses = fac.courses
                adm.save(update_fields=["faculty_courses"])

        # Check if auth.User exists for this faculty / admin
        user_obj = User.objects.filter(Q(email__iexact=email) | Q(username__iexact=fac.name)).first()
        if not user_obj:
            base_username = fac.name.strip()
            username = base_username
            idx = 1
            while User.objects.filter(username__iexact=username).exists():
                username = f"{base_username}_{idx}"
                idx += 1

            name_parts = fac.name.strip().split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            user_obj = User.objects.create(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                password=make_password(fac.password or "Faculty@123"),
                is_staff=True,
                is_superuser=fac.is_admin,
                is_active=True,
            )
        else:
            if not user_obj.is_staff:
                user_obj.is_staff = True
                user_obj.save(update_fields=["is_staff"])


def admin_list_view(request):
    sync_faculty_and_admin_users()
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    q = request.GET.get("q", "").strip()
    role_filter = request.GET.get("role", "").strip()
    
    # Show all administration and faculty personnel (superusers, staff, and faculty)
    admins = User.objects.filter(Q(is_superuser=True) | Q(is_staff=True)).order_by("-is_superuser", "-date_joined")

    if q:
        admins = admins.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )

    # Compute breakdown counts across all registered members
    all_users = User.objects.filter(Q(is_superuser=True) | Q(is_staff=True))
    superusers_count = 0
    faculty_count = 0
    staff_count = 0
    for u in all_users:
        p = get_admin_profile(u)
        if u.is_superuser:
            superusers_count += 1
        if p and p.is_faculty:
            faculty_count += 1
        if p and p.is_staff_role:
            staff_count += 1

    # Prepare enhanced items with role info and courses
    admin_items = []
    for a in admins:
        prof = get_admin_profile(a)
        fac_rec = Faculty.objects.filter(Q(admin_account=prof) | Q(email__iexact=a.email), is_active=True).first()
        is_fac = bool((prof and prof.is_faculty) or fac_rec)
        is_adm = a.is_superuser
        is_stf = bool(prof and prof.is_staff_role)
        
        # Apply role filter if requested
        if role_filter == "admin" and not is_adm:
            continue
        if role_filter == "faculty" and not is_fac:
            continue
        if role_filter == "staff" and not is_stf:
            continue

        raw_courses = (fac_rec.courses if fac_rec and fac_rec.courses else (prof.faculty_courses if prof else "")) or ""
        courses_list = [c.strip() for c in raw_courses.split(",") if c.strip()]

        admin_items.append({
            "user": a,
            "id": a.id,
            "username": a.username,
            "email": a.email,
            "first_name": a.first_name,
            "last_name": a.last_name,
            "date_joined": a.date_joined,
            "last_login": a.last_login,
            "is_superuser": a.is_superuser,
            "is_admin": is_adm,
            "is_faculty": is_fac,
            "is_staff": is_stf,
            "faculty_record": fac_rec,
            "courses_list": courses_list,
            "faculty_courses": raw_courses,
            "total_courses": len(courses_list),
            "has_pending_course_request": bool(prof and prof.has_pending_course_request),
            "pending_courses_list": prof.pending_courses_list if prof else [],
            "pending_courses_str": prof.pending_faculty_courses if prof else "",
            "course_request_status": prof.course_request_status if prof else "",
            "course_request_date": prof.course_request_date if prof else None,
        })

    context = {
        "user": user,
        "admins": admin_items,
        "total_admins": len(admin_items),
        "total_members_count": all_users.count(),
        "superusers_count": superusers_count,
        "faculty_count": faculty_count,
        "staff_count": staff_count,
        "query": q,
        "role_filter": role_filter,
        "course_categories": Student.COURSE_CATEGORIES,
        "pending_course_requests_count": Admin.objects.filter(course_request_status='Pending').count(),
    }
    return render(request, "management/admin_list.html", context)


def admin_create_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    # Only Superusers can register new administrators
    if not user.is_superuser:
        messages.error(
            request, "Permission denied: Only Superusers can register new administrators."
        )
        return redirect("admin_list")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        role_admin = request.POST.get("role_admin") == "1" or request.POST.get("is_superuser") == "1"
        role_faculty = request.POST.get("role_faculty") == "1"
        role_staff = request.POST.get("role_staff") == "1"

        if not (role_admin or role_faculty or role_staff):
            messages.error(request, "Please select at least one role (Admin, Faculty, or Staff)!")
            return redirect("admin_list")

        if not (username and email and password):
            messages.error(request, "Username, email, and password are required!")
            return redirect("admin_list")

        if password != confirm_password:
            messages.error(request, "Password and Confirm Password do not match!")
            return redirect("admin_list")

        if User.objects.filter(username__iexact=username).exists():
            messages.error(request, f"Username '{username}' is already taken!")
            return redirect("admin_list")

        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, f"An account with email '{email}' already exists!")
            return redirect("admin_list")

        new_admin = User.objects.create(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=make_password(password),
            is_superuser=role_admin,
            is_staff=True,
            is_active=True,
        )

        full_name = f"{first_name} {last_name}".strip() or username
        admin_prof, _ = Admin.objects.get_or_create(
            email=email,
            defaults={
                "name": full_name,
                "password": new_admin.password,
            }
        )
        admin_prof.name = full_name
        admin_prof.is_faculty = role_faculty
        admin_prof.is_staff_role = role_staff
        admin_prof.save()

        if role_faculty:
            fac, _ = Faculty.objects.get_or_create(
                admin_account=admin_prof,
                defaults={
                    "name": full_name,
                    "email": email,
                    "phone": admin_prof.phone or "",
                    "is_admin": role_admin,
                    "is_active": True,
                    "courses": admin_prof.faculty_courses or "",
                    "password": admin_prof.password or "",
                }
            )
            fac.name = full_name
            fac.email = email
            fac.is_admin = role_admin
            fac.is_active = True
            fac.save()

        roles_assigned = []
        if role_admin: roles_assigned.append("Admin")
        if role_faculty: roles_assigned.append("Faculty")
        if role_staff: roles_assigned.append("Staff")

        messages.success(
            request, f"Account '{new_admin.username}' created successfully with role(s): {', '.join(roles_assigned)}!"
        )

    return redirect("admin_list")


def admin_edit_view(request, admin_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    # Only Superusers can update administrator accounts
    if not user.is_superuser:
        messages.error(
            request, "Permission denied: Only Superusers can edit administrator accounts."
        )
        return redirect("admin_list")

    target_admin = User.objects.filter(id=admin_id).first()
    if not target_admin:
        messages.error(request, "Administrator not found.")
        return redirect("admin_list")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        new_password = request.POST.get("new_password", "").strip()

        role_admin = request.POST.get("role_admin") == "1" or request.POST.get("is_superuser") == "1"
        role_faculty = request.POST.get("role_faculty") == "1"
        role_staff = request.POST.get("role_staff") == "1"

        if not (role_admin or role_faculty or role_staff):
            messages.error(request, "Please select at least one role (Admin, Faculty, or Staff)!")
            return redirect("admin_list")

        if not (username and email):
            messages.error(request, "Username and email are required!")
            return redirect("admin_list")

        if username != target_admin.username and User.objects.filter(username__iexact=username).exists():
            messages.error(request, f"Username '{username}' is already in use!")
            return redirect("admin_list")

        if email != target_admin.email and User.objects.filter(email__iexact=email).exists():
            messages.error(request, f"Email '{email}' is already in use!")
            return redirect("admin_list")

        target_admin.username = username
        target_admin.email = email
        target_admin.first_name = first_name
        target_admin.last_name = last_name

        # Prevent demoting own superuser status if it's the last superuser
        if target_admin.id == user.id and not role_admin:
            messages.error(request, "You cannot remove your own Admin/Superuser status.")
        else:
            target_admin.is_superuser = role_admin

        target_admin.is_staff = True

        if new_password:
            target_admin.password = make_password(new_password)

        target_admin.save()

        # Sync Admin profile and Faculty profile
        admin_prof = get_admin_profile(target_admin)
        full_name = f"{first_name} {last_name}".strip() or username
        admin_prof.name = full_name
        admin_prof.email = email
        if new_password:
            admin_prof.password = target_admin.password
        admin_prof.is_faculty = role_faculty
        admin_prof.is_staff_role = role_staff
        admin_prof.save()

        if role_faculty:
            fac, _ = Faculty.objects.get_or_create(
                admin_account=admin_prof,
                defaults={
                    "name": full_name,
                    "email": email,
                    "phone": admin_prof.phone or "",
                    "is_admin": role_admin,
                    "is_active": True,
                    "courses": admin_prof.faculty_courses or "",
                    "password": admin_prof.password or "",
                }
            )
            fac.name = full_name
            fac.email = email
            fac.is_admin = role_admin
            fac.is_active = True
            fac.save()
        else:
            # If faculty role removed, deactivate faculty record
            fac = Faculty.objects.filter(admin_account=admin_prof).first()
            if fac:
                fac.is_active = False
                fac.save()

        roles_assigned = []
        if role_admin: roles_assigned.append("Admin")
        if role_faculty: roles_assigned.append("Faculty")
        if role_staff: roles_assigned.append("Staff")

        messages.success(request, f"Account '{target_admin.username}' updated successfully with role(s): {', '.join(roles_assigned)}!")

    return redirect("admin_list")


def admin_delete_view(request, admin_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    # Only Superusers can delete administrator accounts
    if not user.is_superuser:
        messages.error(
            request, "Permission denied: Only Superusers can delete administrator accounts."
        )
        return redirect("admin_list")

    target_admin = User.objects.filter(id=admin_id).first()
    if not target_admin:
        messages.error(request, "Administrator not found.")
        return redirect("admin_list")

    if target_admin.id == user.id:
        messages.error(request, "You cannot delete your own active administrator account!")
        return redirect("admin_list")

    total_superusers = User.objects.filter(is_superuser=True).count()
    if target_admin.is_superuser and total_superusers <= 1:
        messages.error(request, "Cannot delete the only remaining superuser in the system.")
        return redirect("admin_list")

    username = target_admin.username
    target_email = target_admin.email

    # Find and clean up associated Admin profile and Faculty records
    admin_prof = Admin.objects.filter(Q(email__iexact=target_email) | Q(name__iexact=username)).first()
    
    fac_q = Q(email__iexact=target_email)
    if admin_prof:
        fac_q |= Q(admin_account=admin_prof)
    if username:
        fac_q |= Q(name__iexact=username)

    faculties_to_del = list(Faculty.objects.filter(fac_q))
    for fac in faculties_to_del:
        Batch.objects.filter(faculty=fac).update(faculty=None)
        Student.objects.filter(faculty_member=fac).update(faculty_member=None)
        fac.delete()

    if admin_prof:
        admin_prof.delete()

    target_admin.delete()
    messages.success(request, f"Personnel account '{username}' was deleted successfully.")
    return redirect("admin_list")


# --- BATCH-BASED ATTENDANCE MANAGEMENT VIEWS ---


def admin_attendance_hub_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    date_str = request.GET.get("date")
    if date_str:
        try:
            selected_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            selected_date = datetime.date.today()
    else:
        selected_date = datetime.date.today()

    prev_date = selected_date - datetime.timedelta(days=1)
    next_date = selected_date + datetime.timedelta(days=1)

    batch_cards = []
    total_enrolled_all = 0
    total_marked_all = 0
    total_present_all = 0
    total_absent_all = 0
    total_late_all = 0
    total_leave_all = 0

    for slot_tuple in Student.CLASS_TIME_CHOICES:
        slot = slot_tuple[0]
        slot_students = Student.objects.filter(Q(class_time__icontains=slot) | Q(enrolled_batches__batch_time=slot)).distinct()
        if not user.is_superuser:
            slot_students = filter_students_for_faculty(slot_students, user)
        total_students = slot_students.count()
        total_enrolled_all += total_students

        records = Attendance.objects.filter(date=selected_date, student__in=slot_students)
        marked_count = records.count()
        present_count = records.filter(status="Present").count()
        absent_count = records.filter(status="Absent").count()
        late_count = records.filter(status="Late").count()
        leave_count = records.filter(status="Leave").count()

        total_marked_all += marked_count
        total_present_all += present_count
        total_absent_all += absent_count
        total_late_all += late_count
        total_leave_all += leave_count

        if total_students == 0:
            status_label = "No Students"
            status_badge = "badge-muted"
        elif marked_count == 0:
            status_label = "Not Marked"
            status_badge = "badge-danger"
        elif marked_count < total_students:
            status_label = f"Partial ({marked_count}/{total_students})"
            status_badge = "badge-warning"
        else:
            status_label = "Completed"
            status_badge = "badge-success"

        attendance_rate = (
            round(((present_count + late_count) / marked_count) * 100, 1)
            if marked_count > 0
            else 0
        )

        batch_cards.append({
            "slot": slot,
            "total_students": total_students,
            "marked_count": marked_count,
            "present_count": present_count,
            "absent_count": absent_count,
            "late_count": late_count,
            "leave_count": leave_count,
            "status_label": status_label,
            "status_badge": status_badge,
            "attendance_rate": attendance_rate,
            "is_marked": marked_count > 0,
            "is_complete": total_students > 0 and marked_count >= total_students,
        })

    day_rate = (
        round(((total_present_all + total_late_all) / total_marked_all) * 100, 1)
        if total_marked_all > 0
        else 0
    )

    context = {
        "user": user,
        "selected_date": selected_date,
        "selected_date_str": selected_date.isoformat(),
        "prev_date_str": prev_date.isoformat(),
        "next_date_str": next_date.isoformat(),
        "is_today": selected_date == datetime.date.today(),
        "batch_cards": batch_cards,
        "total_enrolled_all": total_enrolled_all,
        "total_marked_all": total_marked_all,
        "total_present_all": total_present_all,
        "total_absent_all": total_absent_all,
        "total_late_all": total_late_all,
        "total_leave_all": total_leave_all,
        "day_rate": day_rate,
    }
    return render(request, "management/attendance_hub.html", context)


def admin_attendance_batch_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    batch_time = request.GET.get("batch") or request.POST.get("batch")
    valid_slots = [c[0] for c in Student.CLASS_TIME_CHOICES]
    if not batch_time or batch_time not in valid_slots:
        batch_time = valid_slots[0]

    date_str = request.GET.get("date") or request.POST.get("date")
    if date_str:
        try:
            selected_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            selected_date = datetime.date.today()
    else:
        selected_date = datetime.date.today()

    batch_id_filter = request.GET.get("batch_id", "").strip() or request.POST.get("batch_id", "").strip()
    slot_batches = Batch.objects.filter(time_slot=batch_time, is_active=True).select_related('faculty').prefetch_related('students')
    selected_batch_obj = None

    if batch_id_filter and batch_id_filter.isdigit():
        selected_batch_obj = slot_batches.filter(id=int(batch_id_filter)).first()

    if selected_batch_obj:
        students = selected_batch_obj.students.all().distinct().order_by("name")
    else:
        students = Student.objects.filter(
            Q(class_time__icontains=batch_time) | 
            Q(enrolled_batches__batch_time=batch_time) |
            Q(assigned_batches__time_slot=batch_time)
        ).distinct().order_by("name")

    if not user.is_superuser:
        students = filter_students_for_faculty(students, user)

    if request.method == "POST":
        saved_count = 0
        present_cnt = 0
        absent_cnt = 0
        late_cnt = 0
        leave_cnt = 0

        for student in students:
            st = request.POST.get(f"status_{student.id}")
            if not st:
                continue
            if st not in ["Present", "Absent", "Late", "Leave"]:
                st = "Present"
            remarks = request.POST.get(f"remarks_{student.id}", "").strip()

            Attendance.objects.update_or_create(
                student=student,
                date=selected_date,
                defaults={
                    "status": st,
                    "time_slot": batch_time,
                    "remarks": remarks,
                    "marked_by": user.username,
                },
            )
            saved_count += 1
            if st == "Present":
                present_cnt += 1
            elif st == "Absent":
                absent_cnt += 1
            elif st == "Late":
                late_cnt += 1
            elif st == "Leave":
                leave_cnt += 1

        messages.success(
            request,
            f"Attendance for batch '{batch_time}' on {selected_date.strftime('%b %d, %Y')} saved successfully! "
            f"({present_cnt} Present, {absent_cnt} Absent, {late_cnt} Late, {leave_cnt} Leave)",
        )
        return redirect(
            f"{request.path}?batch={batch_time}&date={selected_date.isoformat()}"
        )

    # Prepare student rows with existing attendance
    existing_records = {
        a.student_id: a
        for a in Attendance.objects.filter(date=selected_date, student__in=students)
    }

    student_rows = []
    marked_count = 0
    batch_present = 0
    batch_absent = 0
    batch_late = 0
    batch_leave = 0
    batch_on_leave_count = 0

    for s in students:
        rec = existing_records.get(s.id)
        is_on_leave_date = s.is_on_leave_on(selected_date)
        if is_on_leave_date:
            batch_on_leave_count += 1

        if is_on_leave_date:
            if rec and rec.status == "Leave":
                current_status = "Leave"
                current_remarks = rec.remarks or (f"On Leave: {s.leave_reason}" if s.leave_reason else "On Leave")
            elif rec and ("On Leave" in (rec.remarks or "") or not rec.remarks or rec.status in ["Absent", "Present", "Late"]):
                current_status = "Leave"
                current_remarks = rec.remarks or (f"On Leave: {s.leave_reason}" if s.leave_reason else "On Leave")
            elif rec:
                current_status = rec.status
                current_remarks = rec.remarks
            else:
                current_status = "Leave"
                current_remarks = f"On Leave: {s.leave_reason}" if s.leave_reason else "On Leave"
        else:
            current_status = rec.status if rec else "Present"
            current_remarks = rec.remarks if rec else ""

        has_record = rec is not None
        if has_record:
            marked_count += 1
            if current_status == "Present":
                batch_present += 1
            elif current_status == "Absent":
                batch_absent += 1
            elif current_status == "Late":
                batch_late += 1
            elif current_status == "Leave":
                batch_leave += 1
        elif is_on_leave_date:
            batch_leave += 1

        student_rows.append({
            "student": s,
            "status": current_status,
            "remarks": current_remarks,
            "has_record": has_record,
            "is_on_leave_date": is_on_leave_date,
            "leave_reason": s.leave_reason,
            "stats": s.attendance_stats,
        })

    prev_date = selected_date - datetime.timedelta(days=1)
    next_date = selected_date + datetime.timedelta(days=1)

    context = {
        "user": user,
        "batch_time": batch_time,
        "valid_slots": valid_slots,
        "selected_date": selected_date,
        "selected_date_str": selected_date.isoformat(),
        "prev_date_str": prev_date.isoformat(),
        "next_date_str": next_date.isoformat(),
        "is_today": selected_date == datetime.date.today(),
        "students_count": students.count(),
        "student_rows": student_rows,
        "marked_count": marked_count,
        "batch_present": batch_present,
        "batch_absent": batch_absent,
        "batch_late": batch_late,
        "batch_leave": batch_leave,
        "batch_on_leave_count": batch_on_leave_count,
        "slot_batches": slot_batches,
        "selected_batch_id": batch_id_filter if selected_batch_obj else "",
        "selected_batch_obj": selected_batch_obj,
    }
    return render(request, "management/attendance_batch.html", context)


def admin_attendance_report_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    valid_slots = [c[0] for c in Student.CLASS_TIME_CHOICES]
    selected_batch = request.GET.get("batch", "All")

    today = datetime.date.today()
    try:
        month = int(request.GET.get("month", today.month))
        year = int(request.GET.get("year", today.year))
    except (ValueError, TypeError):
        month = today.month
        year = today.year

    _, num_days = calendar.monthrange(year, month)
    days_list = list(range(1, num_days + 1))
    month_name = calendar.month_name[month]

    students_qs = Student.objects.all().order_by("class_time", "name")
    if not user.is_superuser:
        students_qs = filter_students_for_faculty(students_qs, user)
    if selected_batch and selected_batch != "All" and selected_batch in valid_slots:
        students_qs = students_qs.filter(Q(class_time__icontains=selected_batch) | Q(enrolled_batches__batch_time=selected_batch)).distinct()

    start_date = datetime.date(year, month, 1)
    end_date = datetime.date(year, month, num_days)

    records = Attendance.objects.filter(
        date__range=[start_date, end_date],
        student__in=students_qs,
    ).select_related("student")

    att_map = {}
    for r in records:
        att_map[(r.student_id, r.date.day)] = r

    matrix_rows = []
    day_present_totals = {d: 0 for d in days_list}
    day_absent_totals = {d: 0 for d in days_list}

    for s in students_qs:
        daily = []
        p_count = 0
        a_count = 0
        l_count = 0
        le_count = 0

        for d in days_list:
            rec = att_map.get((s.id, d))
            if rec:
                status = rec.status
                daily.append(status)
                if status == "Present":
                    p_count += 1
                    day_present_totals[d] += 1
                elif status == "Absent":
                    a_count += 1
                    day_absent_totals[d] += 1
                elif status == "Late":
                    l_count += 1
                    day_present_totals[d] += 1
                elif status == "Leave":
                    le_count += 1
            else:
                daily.append("")

        total_marked = p_count + a_count + l_count + le_count
        pct = (
            round(((p_count + l_count) / total_marked) * 100, 1)
            if total_marked > 0
            else 0
        )

        matrix_rows.append({
            "student": s,
            "daily": daily,
            "p_count": p_count,
            "a_count": a_count,
            "l_count": l_count,
            "le_count": le_count,
            "total_marked": total_marked,
            "pct": pct,
        })

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="attendance_{month_name}_{year}.csv"'
        writer = csv.writer(response)
        header = ["Student Name", "Email", "Batch Time", "Course"] + [str(d) for d in days_list] + ["Present", "Absent", "Late", "Leave", "Percentage"]
        writer.writerow(header)
        for row in matrix_rows:
            writer.writerow([
                row["student"].name,
                row["student"].email,
                row["student"].class_time or "",
                row["student"].course or "",
            ] + [d or "-" for d in row["daily"]] + [
                row["p_count"],
                row["a_count"],
                row["l_count"],
                row["le_count"],
                f"{row['pct']}%",
            ])
        return response

    months_list = [(i, calendar.month_name[i]) for i in range(1, 13)]
    years_list = [year - 1, year, year + 1]

    context = {
        "user": user,
        "matrix_rows": matrix_rows,
        "days_list": days_list,
        "selected_batch": selected_batch,
        "valid_slots": valid_slots,
        "month": month,
        "month_name": month_name,
        "year": year,
        "months_list": months_list,
        "years_list": years_list,
        "total_students": students_qs.count(),
    }
    return render(request, "management/attendance_report.html", context)

# --- BATCH TRANSFER VIEW ---


def admin_batch_transfer_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    all_batches_qs = (
        Batch.objects.filter(is_active=True)
        .select_related("faculty")
        .prefetch_related("students")
        .order_by("time_slot", "name")
    )
    if not user.is_superuser:
        all_batches_qs = filter_batches_for_faculty(all_batches_qs, user)
    all_batches = all_batches_qs
    unassigned_count = filter_students_for_faculty(Student.objects.filter(assigned_batch__isnull=True), user).count()

    if request.method == "POST":
        source_batch_param = request.POST.get("source_batch", "").strip()
        target_batch_param = request.POST.get("target_batch", "").strip()
        selected_student_ids = request.POST.getlist("student_ids")

        if not source_batch_param:
            messages.error(request, "Please select the source batch.")
            return redirect(f"{reverse('admin_batch_transfer')}?source_batch={source_batch_param}&target_batch={target_batch_param}")

        if not target_batch_param:
            messages.error(request, "Please select the destination (target) batch.")
            return redirect(f"{reverse('admin_batch_transfer')}?source_batch={source_batch_param}&target_batch={target_batch_param}")

        if source_batch_param == target_batch_param:
            messages.error(request, "Source and destination batches cannot be the same.")
            return redirect(f"{reverse('admin_batch_transfer')}?source_batch={source_batch_param}&target_batch={target_batch_param}")

        if not selected_student_ids:
            messages.error(request, "Please select at least one student to transfer.")
            return redirect(f"{reverse('admin_batch_transfer')}?source_batch={source_batch_param}&target_batch={target_batch_param}")

        # Resolve Source Batch
        source_batch_obj = None
        if source_batch_param != "unassigned":
            source_batch_obj = Batch.objects.filter(id=source_batch_param).first()
            source_display = f"{source_batch_obj.name} ({source_batch_obj.time_slot})" if source_batch_obj else "Source Batch"
        else:
            source_display = "Unassigned Students"

        # Resolve Target Batch
        target_batch_obj = None
        if target_batch_param != "unassign":
            target_batch_obj = Batch.objects.filter(id=target_batch_param).first()
            if not target_batch_obj:
                messages.error(request, "Destination batch not found.")
                return redirect(f"{reverse('admin_batch_transfer')}?source_batch={source_batch_param}&target_batch={target_batch_param}")
            target_display = f"{target_batch_obj.name} ({target_batch_obj.time_slot})"
        else:
            target_display = "Unassigned"

        students_to_transfer = Student.objects.filter(id__in=selected_student_ids)
        transferred_count = 0
        student_names = []

        for student in students_to_transfer:
            # 1. Remove from all currently assigned batches
            for b in student.assigned_batches.all():
                b.students.remove(student)

            # 2. Assign to target batch
            if target_batch_obj:
                target_batch_obj.students.add(student)
                student.assigned_batch = target_batch_obj
                student.class_time = target_batch_obj.time_slot

                # Sync StudentBatch record
                StudentBatch.objects.filter(student=student).delete()
                StudentBatch.objects.create(student=student, batch_time=target_batch_obj.time_slot)

                # Sync faculty member if target batch has assigned instructor
                if target_batch_obj.faculty:
                    student.faculty_member = target_batch_obj.faculty
                    student.faculty = target_batch_obj.faculty.name
            else:
                student.assigned_batch = None

            student.save()
            transferred_count += 1
            student_names.append(student.name)

        names_preview = ", ".join(student_names[:3])
        if len(student_names) > 3:
            names_preview += f" and {len(student_names) - 3} more"

        messages.success(
            request,
            f"Successfully transferred {transferred_count} student(s) ({names_preview}) from '{source_display}' to '{target_display}'!"
        )
        redirect_source = target_batch_param if target_batch_param != "unassign" else source_batch_param
        return redirect(f"{reverse('admin_batch_transfer')}?source_batch={redirect_source}")

    # GET request
    source_batch_param = request.GET.get("source_batch", "").strip()
    target_batch_param = request.GET.get("target_batch", "").strip()
    q = request.GET.get("q", "").strip()

    source_batch_obj = None
    if source_batch_param == "unassigned":
        source_batch_id = "unassigned"
    elif source_batch_param:
        source_batch_obj = Batch.objects.filter(id=source_batch_param, is_active=True).first()
        source_batch_id = str(source_batch_obj.id) if source_batch_obj else ""
    else:
        # Default: Pick the first batch with students, or the first available batch, or unassigned
        batch_with_students = next((b for b in all_batches if b.student_count > 0), None)
        if batch_with_students:
            source_batch_obj = batch_with_students
            source_batch_id = str(batch_with_students.id)
        elif all_batches.exists():
            source_batch_obj = all_batches.first()
            source_batch_id = str(source_batch_obj.id)
        elif unassigned_count > 0:
            source_batch_id = "unassigned"
        else:
            source_batch_id = ""

    students = []
    if source_batch_id == "unassigned":
        students_qs = Student.objects.filter(assigned_batch__isnull=True).order_by("name")
    elif source_batch_obj:
        students_qs = source_batch_obj.students.all().order_by("name")
    else:
        students_qs = Student.objects.none()

    if not user.is_superuser:
        students_qs = filter_students_for_faculty(students_qs, user)

    if q:
        students_qs = students_qs.filter(
            Q(name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q) | Q(course__icontains=q)
        )
    students = list(students_qs)

    target_batch_obj = None
    if target_batch_param and target_batch_param != "unassign" and target_batch_param.isdigit():
        target_batch_obj = Batch.objects.filter(id=int(target_batch_param), is_active=True).first()

    context = {
        "user": user,
        "all_batches": all_batches,
        "unassigned_count": unassigned_count,
        "source_batch_id": source_batch_id,
        "source_batch_obj": source_batch_obj,
        "target_batch_id": target_batch_param,
        "target_batch_obj": target_batch_obj,
        "students": students,
        "total_source_students": len(students),
        "q": q,
    }
    return render(request, "management/batch_transfer.html", context)

# --- DAILY WORK REPORT MANAGEMENT VIEW ---


def admin_daily_work_report_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    today = datetime.date.today()
    date_str = request.GET.get("date")
    if date_str:
        try:
            selected_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            selected_date = today
    else:
        selected_date = today

    prev_date = selected_date - datetime.timedelta(days=1)
    next_date = selected_date + datetime.timedelta(days=1)

    batch_param = request.GET.get("batch_id", "").strip() or request.GET.get("batch", "").strip()
    batch_filter = ""
    batch_id_filter = ""
    selected_batch_obj = None

    if batch_param.isdigit():
        batch_id_filter = batch_param
    elif batch_param.startswith("batch_"):
        batch_id_filter = batch_param.replace("batch_", "")
    elif batch_param:
        batch_filter = batch_param

    if batch_id_filter and batch_id_filter.isdigit():
        selected_batch_obj = Batch.objects.filter(id=int(batch_id_filter)).first()

    course_filter = request.GET.get("course", "").strip()
    q = request.GET.get("q", "").strip()

    # Query all students matching optional batch filter
    students_scope = Student.objects.all()
    if not user.is_superuser:
        students_scope = filter_students_for_faculty(students_scope, user)
    if selected_batch_obj:
        students_scope = students_scope.filter(
            Q(assigned_batch=selected_batch_obj) | Q(assigned_batches=selected_batch_obj)
        ).distinct()
    elif batch_filter:
        students_scope = students_scope.filter(
            Q(class_time__icontains=batch_filter)
            | Q(enrolled_batches__batch_time=batch_filter)
            | Q(assigned_batches__time_slot=batch_filter)
            | Q(assigned_batch__time_slot=batch_filter)
        ).distinct()

    if course_filter:
        students_scope = students_scope.filter(course__icontains=course_filter)

    total_students_scoped = students_scope.count()

    # Query reports for selected_date
    reports_qs = DailyWorkReport.objects.filter(
        date=selected_date,
        student__in=students_scope
    ).select_related("student", "faculty", "student__assigned_batch").prefetch_related("student__assigned_batches")

    if course_filter:
        reports_qs = reports_qs.filter(course=course_filter)

    if q:
        reports_qs = reports_qs.filter(
            Q(student__name__icontains=q)
            | Q(student__email__icontains=q)
            | Q(course__icontains=q)
            | Q(running_topic__icontains=q)
            | Q(class_work__icontains=q)
            | Q(class_work_time__icontains=q)
            | Q(home_work__icontains=q)
            | Q(home_work_time__icontains=q)
        )

    reports = list(reports_qs.order_by("-created_at"))

    submitted_student_ids = set(r.student_id for r in reports)
    submitted_count = len(submitted_student_ids)

    # Pending students for this date
    pending_students = list(students_scope.exclude(id__in=submitted_student_ids).select_related("assigned_batch", "faculty_member").prefetch_related("assigned_batches").order_by("name"))
    pending_count = len(pending_students)

    # Fetch active batches for batch-wise breakdown & dropdown filter
    all_batches_qs = Batch.objects.filter(is_active=True).prefetch_related('students').select_related('faculty').order_by('time_slot', 'name')
    if not user.is_superuser:
        all_batches_qs = filter_batches_for_faculty(all_batches_qs, user)
    all_batches = list(all_batches_qs)

    # Determine which batches to show in the Batch-Based view
    if selected_batch_obj:
        target_batches = [selected_batch_obj]
    elif batch_filter:
        target_batches = [b for b in all_batches if batch_filter.lower() in b.time_slot.lower()]
    else:
        target_batches = all_batches

    # Build batch groups data for selected date
    batch_groups = []
    covered_student_ids = set()

    for b in target_batches:
        b_students_qs = b.students.all().order_by("name")
        if not user.is_superuser:
            b_students_qs = filter_students_for_faculty(b_students_qs, user)
        if course_filter:
            b_students_qs = b_students_qs.filter(course__icontains=course_filter)
        b_students = list(b_students_qs)
        b_student_ids = set(s.id for s in b_students)
        covered_student_ids.update(b_student_ids)

        b_reports = [r for r in reports if r.student_id in b_student_ids]
        b_submitted_student_ids = set(r.student_id for r in b_reports)
        b_pending_students = [s for s in b_students if s.id not in b_submitted_student_ids]

        b_total = len(b_students)
        b_submitted = len(b_submitted_student_ids)
        b_pending = len(b_pending_students)
        b_rate = round((b_submitted / b_total * 100)) if b_total > 0 else 0

        batch_groups.append({
            "batch": b,
            "total_students": b_total,
            "submitted_count": b_submitted,
            "pending_count": b_pending,
            "submission_rate": b_rate,
            "reports": b_reports,
            "pending_students": b_pending_students,
            "is_complete": b_total > 0 and b_pending == 0,
            "has_reports": len(b_reports) > 0,
            "has_activity": b_total > 0 or len(b_reports) > 0,
        })

    # Catch any students or reports not covered in named batches
    unassigned_reports = [r for r in reports if r.student_id not in covered_student_ids]
    unassigned_pending = [s for s in pending_students if s.id not in covered_student_ids]

    unassigned_group = None
    if unassigned_reports or unassigned_pending:
        unassigned_total = len(set(r.student_id for r in unassigned_reports)) + len(unassigned_pending)
        unassigned_sub_count = len(set(r.student_id for r in unassigned_reports))
        unassigned_rate = round((unassigned_sub_count / unassigned_total * 100)) if unassigned_total > 0 else 0
        unassigned_group = {
            "is_unassigned": True,
            "title": "Flexible / Other Batches",
            "total_students": unassigned_total,
            "submitted_count": unassigned_sub_count,
            "pending_count": len(unassigned_pending),
            "submission_rate": unassigned_rate,
            "reports": unassigned_reports,
            "pending_students": unassigned_pending,
            "has_reports": len(unassigned_reports) > 0,
        }

    class_time_choices = [c[0] for c in Student.CLASS_TIME_CHOICES]
    course_categories = Student.COURSE_CATEGORIES

    context = {
        "user": user,
        "selected_date": selected_date,
        "selected_date_str": selected_date.isoformat(),
        "prev_date_str": prev_date.isoformat(),
        "next_date_str": next_date.isoformat(),
        "is_today": selected_date == today,
        "reports": reports,
        "total_reports": len(reports),
        "submitted_count": submitted_count,
        "pending_count": pending_count,
        "pending_students": pending_students,
        "total_students_scoped": total_students_scoped,
        "batch_filter": batch_param,
        "batch_id_filter": batch_id_filter,
        "selected_batch_obj": selected_batch_obj,
        "all_batches": all_batches,
        "batch_groups": batch_groups,
        "unassigned_group": unassigned_group,
        "course_filter": course_filter,
        "class_time_choices": class_time_choices,
        "course_categories": course_categories,
        "q": q,
    }
    return render(request, "management/daily_work_report.html", context)


# --- FACULTY MANAGEMENT VIEWS (ADMIN CREATED ONLY & ADMIN FACULTY TOGGLE) ---


def faculty_list_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    faculties = Faculty.objects.all().order_by("-is_admin", "name")
    q = request.GET.get("q", "").strip()
    dept_filter = request.GET.get("department", "").strip()

    if q:
        faculties = faculties.filter(
            Q(name__icontains=q)
            | Q(department__icontains=q)
            | Q(specialization__icontains=q)
            | Q(courses__icontains=q)
            | Q(email__icontains=q)
        )

    if dept_filter:
        faculties = faculties.filter(department=dept_filter)

    departments = list(Student.COURSE_CATEGORIES.keys())

    admin_prof = get_admin_profile(user)
    # Get linked faculty record for current admin if exists
    admin_fac_profile = Faculty.objects.filter(admin_account=admin_prof).first()

    context = {
        "user": user,
        "admin_prof": admin_prof,
        "faculties": faculties,
        "query": q,
        "dept_filter": dept_filter,
        "departments": departments,
        "course_categories": Student.COURSE_CATEGORIES,
        "total_faculty_count": Faculty.objects.count(),
        "admin_fac_profile": admin_fac_profile,
    }
    return render(request, "management/faculty_list.html", context)


def faculty_create_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    departments = list(Student.COURSE_CATEGORIES.keys())
    course_categories = Student.COURSE_CATEGORIES

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip() or None
        phone = request.POST.get("phone", "").strip()
        department = request.POST.get("department", "").strip()
        specialization = request.POST.get("specialization", "").strip()
        selected_courses = request.POST.getlist("courses")
        is_active = request.POST.get("is_active") == "on"
        is_admin = False

        if not (name and department):
            messages.error(request, "Faculty Name and Primary Department are required!")
            return render(
                request,
                "management/faculty_form.html",
                {
                    "user": user,
                    "departments": departments,
                    "course_categories": course_categories,
                },
            )

        courses_str = ", ".join(c.strip() for c in selected_courses if c.strip())

        faculty = Faculty.objects.create(
            name=name,
            email=email,
            phone=phone,
            department=department,
            specialization=specialization,
            courses=courses_str,
            is_admin=is_admin,
            is_active=is_active,
            created_by=(f'{user.first_name} {user.last_name}'.strip() or user.username),
        )

        sync_faculty_and_admin_users()
        messages.success(request, f"Faculty instructor '{faculty.name}' created successfully!")
        return redirect("admin_faculty_list")

    return render(
        request,
        "management/faculty_form.html",
        {
            "user": user,
            "departments": departments,
            "course_categories": course_categories,
        },
    )


def faculty_edit_view(request, faculty_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    faculty = Faculty.objects.filter(id=faculty_id).first()
    if not faculty:
        messages.error(request, "Faculty record not found.")
        return redirect("admin_faculty_list")

    departments = list(Student.COURSE_CATEGORIES.keys())
    course_categories = Student.COURSE_CATEGORIES

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip() or None
        phone = request.POST.get("phone", "").strip()
        department = request.POST.get("department", "").strip()
        specialization = request.POST.get("specialization", "").strip()
        selected_courses = request.POST.getlist("courses")
        is_active = request.POST.get("is_active") == "on"
        is_admin = faculty.is_admin

        if not (name and department):
            messages.error(request, "Faculty Name and Primary Department are required!")
            return render(
                request,
                "management/faculty_form.html",
                {
                    "user": user,
                    "faculty": faculty,
                    "departments": departments,
                    "course_categories": course_categories,
                },
            )

        courses_str = ", ".join(c.strip() for c in selected_courses if c.strip())

        faculty.name = name
        faculty.email = email
        faculty.phone = phone
        faculty.department = department
        faculty.specialization = specialization
        faculty.courses = courses_str
        faculty.is_active = is_active
        faculty.is_admin = is_admin
        faculty.save()

        # If linked to an admin account, keep admin user in sync
        if faculty.admin_account:
            adm = faculty.admin_account
            adm.name = name
            adm.faculty_department = department
            adm.faculty_specialization = specialization
            adm.faculty_courses = courses_str
            adm.phone = phone
            adm.save()

        messages.success(request, f"Faculty instructor '{faculty.name}' updated successfully!")
        return redirect("admin_faculty_list")

    return render(
        request,
        "management/faculty_form.html",
        {
            "user": user,
            "faculty": faculty,
            "departments": departments,
            "course_categories": course_categories,
        },
    )


def faculty_delete_view(request, faculty_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    faculty = Faculty.objects.filter(id=faculty_id).first()
    if not faculty:
        messages.error(request, "Faculty record not found.")
        return redirect("admin_faculty_list")

    name = faculty.name
    fac_email = faculty.email
    admin_account = faculty.admin_account

    Batch.objects.filter(faculty=faculty).update(faculty=None)
    Student.objects.filter(faculty_member=faculty).update(faculty_member=None)

    faculty.delete()

    if admin_account:
        associated_user = User.objects.filter(Q(email__iexact=admin_account.email) | Q(email__iexact=fac_email)).first()
        if associated_user and not associated_user.is_superuser:
            associated_user.delete()
            admin_account.delete()
        elif admin_account:
            admin_account.is_faculty = False
            admin_account.save()
    elif fac_email:
        associated_user = User.objects.filter(email__iexact=fac_email).first()
        if associated_user and not associated_user.is_superuser:
            associated_user.delete()

    messages.success(request, f"Faculty instructor '{name}' removed successfully.")
    return redirect("admin_faculty_list")


def toggle_admin_faculty_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    admin_prof = get_admin_profile(user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "enable":
            dept = request.POST.get("department", "Development Courses").strip()
            spec = request.POST.get("specialization", "").strip()
            selected_courses = request.POST.getlist("courses")
            courses_str = ", ".join(c.strip() for c in selected_courses if c.strip())

            admin_prof.is_faculty = True
            admin_prof.faculty_department = dept
            admin_prof.faculty_specialization = spec
            admin_prof.faculty_courses = courses_str
            admin_prof.save()

            fac, created = Faculty.objects.get_or_create(
                admin_account=admin_prof,
                defaults={
                    "name": admin_prof.name,
                    "email": admin_prof.email,
                    "phone": admin_prof.phone or "",
                    "department": dept,
                    "specialization": spec,
                    "courses": courses_str,
                    "is_admin": True,
                    "is_active": True,
                    "created_by": f"Self ({user.username})",
                },
            )
            if not created:
                fac.name = admin_prof.name
                fac.email = admin_prof.email
                fac.department = dept
                fac.specialization = spec
                fac.courses = courses_str
                fac.is_active = True
                fac.is_admin = True
                fac.save()

            messages.success(request, f"Faculty role enabled for Administrator '{admin_prof.name}'! You are now available for student faculty assignment.")
        else:
            admin_prof.is_faculty = False
            admin_prof.save()
            Faculty.objects.filter(admin_account=admin_prof).delete()
            messages.info(request, f"Faculty role disabled for Administrator '{admin_prof.name}'.")

    return redirect("admin_faculty_list")


# --- BATCH MANAGEMENT VIEWS ---

def admin_batch_list_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    all_batches = Batch.objects.filter(is_active=True).prefetch_related('students').select_related('faculty').order_by('time_slot', 'name')
    if not user.is_superuser:
        all_batches = filter_batches_for_faculty(all_batches, user)
    batches = all_batches
    
    # Filter parameters
    slot_filter = request.GET.get('slot', '').strip()
    faculty_filter = request.GET.get('faculty', '').strip()
    course_filter = request.GET.get('course', '').strip()
    q = request.GET.get('q', '').strip()

    if slot_filter:
        batches = batches.filter(time_slot=slot_filter)
    if faculty_filter:
        batches = batches.filter(
            Q(faculty__id=faculty_filter if faculty_filter.isdigit() else None)
            | Q(faculty__name__icontains=faculty_filter)
        )
    if course_filter:
        batches = batches.filter(course__icontains=course_filter)
    if q:
        batches = batches.filter(
            Q(name__icontains=q)
            | Q(course__icontains=q)
            | Q(faculty__name__icontains=q)
        )

    # Attach display_students to each batch (filtered for faculty)
    batches_list = list(batches)
    for b in batches_list:
        b.display_students = list(filter_students_for_faculty(b.students.all(), user).order_by("name"))
        b.display_student_count = len(b.display_students)
    batches = batches_list

    # All unassigned students who have a time slot (batch assignment is based on time)
    all_unassigned_students = Student.objects.filter(
        assigned_batch__isnull=True,
        assigned_batches__isnull=True
    ).exclude(
        Q(class_time__isnull=True) | Q(class_time__exact='')
    ).distinct().order_by('class_time', 'name')
    if not user.is_superuser:
        all_unassigned_students = filter_students_for_faculty(all_unassigned_students, user)

    # Unassigned students for batch list page: based on time
    if slot_filter:
        unassigned_students = all_unassigned_students.filter(
            Q(class_time__iexact=slot_filter) | Q(class_time__icontains=slot_filter)
        )
    else:
        unassigned_students = all_unassigned_students

    total_batches = Batch.objects.filter(is_active=True).count()
    total_assigned_students = Student.objects.filter(
        Q(assigned_batch__isnull=False) | Q(assigned_batches__isnull=False)
    ).distinct().count()
    total_unassigned_students = all_unassigned_students.count()

    class_time_choices = [c[0] for c in Student.CLASS_TIME_CHOICES]
    course_categories = Student.COURSE_CATEGORIES
    faculties = Faculty.objects.filter(is_active=True).order_by("department", "name")

    context = {
        "user": user,
        "batches": batches,
        "all_batches": all_batches,
        "unassigned_students": unassigned_students,
        "all_unassigned_students": all_unassigned_students,
        "total_batches": total_batches,
        "total_assigned_students": total_assigned_students,
        "total_unassigned_students": total_unassigned_students,
        "class_time_choices": class_time_choices,
        "course_categories": course_categories,
        "faculties": faculties,
        "slot_filter": slot_filter,
        "faculty_filter": faculty_filter,
        "course_filter": course_filter,
        "query": q,
    }
    return render(request, "management/batch_list.html", context)


def admin_batch_create_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    if request.method == "POST":
        time_slot = request.POST.get("time_slot", "").strip()
        faculty_id = request.POST.get("faculty_id", "").strip()
        description = request.POST.get("description", "").strip()
        student_ids = request.POST.getlist("student_ids")

        if not time_slot:
            messages.error(request, "Scheduled Time Slot is required!")
            return redirect("admin_batch_list")

        faculty_member = None
        if faculty_id and faculty_id.isdigit():
            faculty_member = Faculty.objects.filter(id=int(faculty_id)).first()

        # Batch Name is auto-assigned from its unique Batch ID (e.g. Batch 9, Batch 14)
        batch = Batch.objects.create(
            name="Temporary Batch",
            course="",
            time_slot=time_slot,
            faculty=faculty_member,
            description=description,
        )
        batch.name = f"Batch {batch.id}"
        batch.save(update_fields=["name"])

        if student_ids:
            enrolled = Student.objects.filter(id__in=student_ids)
            batch.students.add(*enrolled)
            enrolled.update(assigned_batch=batch)

        messages.success(request, f"{batch.name} created successfully with {batch.students.count()} student(s) enrolled!")
        return redirect("admin_batch_list")

    return redirect("admin_batch_list")


def admin_batch_edit_view(request, batch_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    batch = Batch.objects.filter(id=batch_id).first()
    if not batch:
        messages.error(request, "Batch not found.")
        return redirect("admin_batch_list")

    if request.method == "POST":
        time_slot = request.POST.get("time_slot", "").strip()
        faculty_id = request.POST.get("faculty_id", "").strip()
        description = request.POST.get("description", "").strip()
        student_ids = request.POST.getlist("student_ids")

        if not time_slot:
            messages.error(request, "Scheduled Time Slot is required!")
            return redirect("admin_batch_list")

        faculty_member = None
        if faculty_id and faculty_id.isdigit():
            faculty_member = Faculty.objects.filter(id=int(faculty_id)).first()

        # Batch Name is permanently tied to Batch ID
        batch.name = f"Batch {batch.id}"
        batch.course = ""
        batch.time_slot = time_slot
        batch.faculty = faculty_member
        batch.description = description
        batch.save()

        # Sync enrolled students only if student_ids is present in request.POST
        if "student_ids" in request.POST:
            current_student_ids = set(batch.students.values_list('id', flat=True))
            new_student_ids = set(int(s) for s in student_ids if s.isdigit())

            to_remove = current_student_ids - new_student_ids
            to_add = new_student_ids - current_student_ids

            if to_remove:
                removed_qs = Student.objects.filter(id__in=to_remove)
                batch.students.remove(*removed_qs)
                removed_qs.filter(assigned_batch=batch).update(assigned_batch=None)

            if to_add:
                added_qs = Student.objects.filter(id__in=to_add)
                batch.students.add(*added_qs)
                added_qs.update(assigned_batch=batch)

        messages.success(request, f"{batch.name} updated successfully.")
        return redirect("admin_batch_list")

    return redirect("admin_batch_list")


def admin_batch_delete_view(request, batch_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    batch = Batch.objects.filter(id=batch_id).first()
    if not batch:
        messages.error(request, "Batch not found.")
        return redirect("admin_batch_list")

    name = batch.name
    # Unassign all students
    batch.students.all().update(assigned_batch=None)
    batch.delete()
    messages.success(request, f"Batch '{name}' deleted. Enrolled students are now unassigned.")
    return redirect("admin_batch_list")


def admin_batch_assign_student_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    if request.method == "POST":
        student_id = request.POST.get("student_id")
        batch_id = request.POST.get("batch_id")
        next_url = request.POST.get("next") or request.GET.get("next") or reverse("admin_batch_list")

        student = Student.objects.filter(id=student_id).first()
        if not student:
            messages.error(request, "Student not found.")
            return redirect(next_url)

        if not user.is_superuser:
            faculty_students = filter_students_for_faculty(Student.objects.all(), user)
            if not faculty_students.filter(id=student.id).exists():
                messages.error(request, "Permission denied: You can only assign batches for your own course students.")
                return redirect(next_url)

        if batch_id == "unassign" or not batch_id:
            for b in student.assigned_batches.all():
                b.students.remove(student)
            student.assigned_batch = None
            student.save()
            messages.success(request, f"Student '{student.name}' is now unassigned from any batch.")
        else:
            batch = Batch.objects.filter(id=batch_id).first()
            if not batch:
                messages.error(request, "Target batch not found.")
                return redirect(next_url)

            for b in student.assigned_batches.all():
                b.students.remove(student)
            batch.students.add(student)
            student.assigned_batch = batch
            student.save()
            messages.success(request, f"Student '{student.name}' assigned to batch '{batch.name}' ({batch.time_slot})!")

        return redirect(next_url)

    return redirect("admin_batch_list")
