from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.models import User
from django.db.models import Q
from Student.models import Student, StudentCourse, Project, Exam, ExamMarks


def get_current_admin(request):
    admin_id = request.session.get("admin_id")
    if admin_id:
        return (
            User.objects.filter(id=admin_id, is_active=True)
            .filter(Q(is_superuser=True) | Q(is_staff=True))
            .first()
        )
    return None


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

    students_count = Student.objects.count()
    projects_count = Project.objects.count()
    exams_count = Exam.objects.count()

    context = {
        "user": user,
        "admin_user": user,
        "total_students": students_count,
        "total_projects": projects_count,
        "total_exams": exams_count,
    }
    return render(request, "management/profile.html", context)


def admin_change_password_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    if request.method == "POST":
        current_password = request.POST.get("current_password")
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")

        if not (current_password and new_password and confirm_password):
            messages.error(request, "Please fill in all password fields!")
            return render(request, "management/change_password.html", {"user": user})

        if not check_password(current_password, user.password):
            messages.error(request, "Current password is incorrect!")
            return render(request, "management/change_password.html", {"user": user})

        if new_password != confirm_password:
            messages.error(request, "New password and Confirm password do not match!")
            return render(request, "management/change_password.html", {"user": user})

        user.password = make_password(new_password)
        user.save()
        messages.success(request, "Your password has been changed successfully!")
        return redirect("admin_profile")

    return render(request, "management/change_password.html", {"user": user})


# --- ADMIN DASHBOARD & STUDENTS ---


def admin_dashboard_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    students = Student.objects.all().order_by("-created_at")
    projects = Project.objects.all().order_by("-submitted_at")
    exams = Exam.objects.all().order_by("-exam_date")
    admins = User.objects.filter(Q(is_superuser=True) | Q(is_staff=True), is_active=True)

    pending_projects_count = Project.objects.filter(status="Submitted").count()
    approved_projects_count = Project.objects.filter(status="Approved").count()

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
    }
    return render(request, "management/dashboard.html", context)


def student_register_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    class_time_choices = [c[0] for c in Student.CLASS_TIME_CHOICES]
    course_categories = Student.COURSE_CATEGORIES

    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        password = request.POST.get("password")
        selected_courses = request.POST.getlist("courses")
        if not selected_courses:
            course_str = request.POST.get("course", "").strip()
            if course_str:
                selected_courses = [c.strip() for c in course_str.split(",") if c.strip()]
        class_time = request.POST.get("class_time", "").strip()
        phone = request.POST.get("phone", "")

        if not (name and email and password and selected_courses):
            messages.error(request, "Please fill in all required fields including at least one course!")
            return render(
                request,
                "management/student_register.html",
                {
                    "user": user,
                    "class_time_choices": class_time_choices,
                    "course_categories": course_categories,
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
                },
            )

        student = Student.objects.create(
            name=name,
            email=email,
            password=make_password(password),
            course=", ".join(selected_courses),
            class_time=class_time,
            phone=phone,
        )
        for c in selected_courses:
            StudentCourse.objects.get_or_create(student=student, course_name=c)

        messages.success(request, f"Student {name} registered successfully with {len(selected_courses)} course(s)!")
        return redirect("admin_student_list")

    return render(
        request,
        "management/student_register.html",
        {
            "user": user,
            "class_time_choices": class_time_choices,
            "course_categories": course_categories,
        },
    )


def student_list_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    students = Student.objects.all().order_by("-created_at")
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
        students = students.filter(class_time=class_time_filter)

    course_categories = Student.COURSE_CATEGORIES
    class_time_choices = [c[0] for c in Student.CLASS_TIME_CHOICES]

    context = {
        "user": user,
        "students": students,
        "query": q,
        "course_filter": course_filter,
        "class_time_filter": class_time_filter,
        "course_categories": course_categories,
        "class_time_choices": class_time_choices,
        "total_students_count": Student.objects.count(),
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

    projects = Project.objects.filter(student=student).prefetch_related("files", "links").order_by("-submitted_at")
    marks_records = ExamMarks.objects.filter(student=student).order_by("-exam__exam_date")

    total_obtained = sum(m.marks_obtained for m in marks_records if m.marks_obtained is not None)
    total_possible = sum(m.exam.total_marks for m in marks_records if m.marks_obtained is not None)
    percentage = (
        round((float(total_obtained) / float(total_possible) * 100), 2)
        if total_possible > 0
        else 0
    )

    context = {
        "user": user,
        "student": student,
        "projects": projects,
        "marks_records": marks_records,
        "total_obtained": total_obtained,
        "total_possible": total_possible,
        "percentage": percentage,
    }
    return render(request, "management/student_detail.html", context)


def student_edit_view(request, student_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    student = Student.objects.filter(id=student_id).first()
    if not student:
        messages.error(request, "Student not found.")
        return redirect("admin_student_list")

    class_time_choices = [c[0] for c in Student.CLASS_TIME_CHOICES]
    course_categories = Student.COURSE_CATEGORIES
    next_url = request.GET.get("next") or request.POST.get("next") or "detail"

    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        selected_courses = request.POST.getlist("courses")
        if not selected_courses:
            course_str = request.POST.get("course", "").strip()
            if course_str:
                selected_courses = [c.strip() for c in course_str.split(",") if c.strip()]

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
                    "next_url": next_url,
                },
            )

        if password:
            student.password = make_password(password)

        student.name = request.POST.get("name")
        student.email = email
        student.course = ", ".join(selected_courses)
        student.class_time = request.POST.get("class_time", "").strip()
        student.phone = request.POST.get("phone")
        student.save()

        # Sync StudentCourse table
        StudentCourse.objects.filter(student=student).exclude(course_name__in=selected_courses).delete()
        for c in selected_courses:
            StudentCourse.objects.get_or_create(student=student, course_name=c)

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
            "next_url": next_url,
        },
    )


def student_delete_view(request, student_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    student = Student.objects.filter(id=student_id).first()
    if not student:
        messages.error(request, "Student not found.")
        return redirect("admin_student_list")

    name = student.name
    student.delete()
    messages.success(request, f"Student '{name}' and all associated records deleted.")
    return redirect("admin_student_list")


# --- STUDENT PROJECTS VIEWS ---


def admin_projects_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    student_id = request.GET.get("student_id")

    projects = Project.objects.select_related("student").prefetch_related("files", "links").order_by("-submitted_at")
    total_projects_count = projects.count()

    if student_id:
        projects = projects.filter(student_id=student_id)

    students = Student.objects.all().order_by("name")

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


# --- EXAMS & MARKS WORKFLOW VIEWS ---


def exam_list_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    q = request.GET.get("q")
    exams = Exam.objects.prefetch_related("students", "marks_records").all().order_by("-exam_date")
    total_exams_count = exams.count()

    if q:
        exams = exams.filter(Q(title__icontains=q) | Q(subject__icontains=q))

    # Prepare stats for each exam
    exam_cards = []
    for exam in exams:
        total_students = exam.students.count()
        marks_records = exam.marks_records.all()
        graded_count = marks_records.filter(marks_obtained__isnull=False, is_absent=False).count()
        absent_count = marks_records.filter(is_absent=True).count()
        pending_count = total_students - (graded_count + absent_count)
        exam_cards.append({
            "exam": exam,
            "total_students": total_students,
            "graded_count": graded_count,
            "absent_count": absent_count,
            "pending_count": pending_count,
        })

    context = {
        "user": user,
        "exam_cards": exam_cards,
        "query": q,
        "total_exams_count": total_exams_count,
    }
    return render(request, "management/exam_list.html", context)


def exam_create_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    students = Student.objects.all().order_by("name")

    if request.method == "POST":
        title = request.POST.get("title")
        subject = request.POST.get("subject")
        exam_date = request.POST.get("exam_date")
        exam_time = request.POST.get("exam_time", "").strip()
        total_marks = request.POST.get("total_marks", "100")
        student_ids = request.POST.getlist("student_ids")

        if not (title and subject and exam_date and total_marks):
            messages.error(request, "Please fill in all required exam fields!")
            return render(
                request,
                "management/exam_form.html",
                {"user": user, "students": students, "is_edit": False},
            )

        exam = Exam.objects.create(
            title=title,
            subject=subject,
            exam_date=exam_date,
            exam_time=exam_time,
            total_marks=float(total_marks),
        )

        if student_ids:
            selected_students = Student.objects.filter(id__in=student_ids)
            exam.students.set(selected_students)
            for s in selected_students:
                ExamMarks.objects.get_or_create(exam=exam, student=s)

        messages.success(request, f"Exam '{title}' created successfully! Now add marks for enrolled students.")
        return redirect("admin_exam_detail", exam_id=exam.id)

    return render(
        request,
        "management/exam_form.html",
        {"user": user, "students": students, "is_edit": False},
    )


def exam_detail_view(request, exam_id):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    exam = Exam.objects.filter(id=exam_id).first()
    if not exam:
        messages.error(request, "Exam not found.")
        return redirect("admin_exam_list")

    # Ensure all enrolled students have an ExamMarks record
    for student in exam.students.all():
        ExamMarks.objects.get_or_create(exam=exam, student=student)

    marks_records = ExamMarks.objects.filter(exam=exam).select_related("student").order_by("student__name")

    graded_records = [m for m in marks_records if m.marks_obtained is not None and not m.is_absent]
    absent_records = [m for m in marks_records if m.is_absent]
    graded_count = len(graded_records)
    absent_count = len(absent_records)
    total_students = marks_records.count()
    pending_count = total_students - graded_count - absent_count

    avg_marks = 0
    if graded_count > 0:
        avg_marks = round(sum(float(m.marks_obtained) for m in graded_records) / graded_count, 2)

    all_students = Student.objects.all().order_by("name")
    enrolled_ids = set(exam.students.values_list("id", flat=True))
    available_students = [s for s in all_students if s.id not in enrolled_ids]

    context = {
        "user": user,
        "exam": exam,
        "marks_records": marks_records,
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
        student_id = request.POST.get("student_id")
        action = request.POST.get("action", "save")
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
            messages.success(request, f"Added {student.name} to exam {exam.title}.")

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

    students = Student.objects.all().order_by("name")
    enrolled_student_ids = list(exam.students.values_list("id", flat=True))

    if request.method == "POST":
        exam.title = request.POST.get("title")
        exam.subject = request.POST.get("subject")
        exam.exam_date = request.POST.get("exam_date")
        exam.exam_time = request.POST.get("exam_time", "").strip()
        exam.total_marks = float(request.POST.get("total_marks", "100"))
        exam.save()

        student_ids = request.POST.getlist("student_ids")
        selected_students = Student.objects.filter(id__in=student_ids)
        exam.students.set(selected_students)

        # Create marks records for newly added students
        for s in selected_students:
            ExamMarks.objects.get_or_create(exam=exam, student=s)

        # Remove marks records for removed students
        ExamMarks.objects.filter(exam=exam).exclude(student__in=selected_students).delete()

        # Recalculate grades for existing marks in case total_marks changed
        for m in exam.marks_records.filter(marks_obtained__isnull=False):
            m.save()

        messages.success(request, f"Exam '{exam.title}' updated successfully!")
        return redirect("admin_exam_detail", exam_id=exam.id)

    return render(
        request,
        "management/exam_form.html",
        {
            "user": user,
            "exam": exam,
            "students": students,
            "enrolled_student_ids": enrolled_student_ids,
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


# --- ADMIN MANAGEMENT OVERVIEW & CRUD ---


def admin_list_view(request):
    user = get_current_admin(request)
    if not user:
        return redirect("admin_login")

    q = request.GET.get("q", "").strip()
    
    # If the user is a superuser, they can see all admins (superusers + staff).
    # If the user is a staff administrator, they cannot see superuser accounts.
    if user.is_superuser:
        admins = User.objects.filter(Q(is_superuser=True) | Q(is_staff=True))
    else:
        admins = User.objects.filter(is_staff=True, is_superuser=False)

    admins = admins.order_by("-date_joined")

    if q:
        admins = admins.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )

    if user.is_superuser:
        all_admins = User.objects.filter(Q(is_superuser=True) | Q(is_staff=True))
        total_admins = all_admins.count()
        superusers_count = all_admins.filter(is_superuser=True).count()
        staff_count = all_admins.filter(is_staff=True, is_superuser=False).count()
    else:
        all_admins = User.objects.filter(is_staff=True, is_superuser=False)
        total_admins = all_admins.count()
        superusers_count = 0
        staff_count = total_admins

    context = {
        "user": user,
        "admins": admins,
        "total_admins": total_admins,
        "superusers_count": superusers_count,
        "staff_count": staff_count,
        "query": q,
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
        is_superuser = request.POST.get("is_superuser") == "1"

        if not (username and email and password):
            messages.error(request, "Username, email, and password are required!")
            return redirect("admin_list")

        if password != confirm_password:
            messages.error(request, "Password and Confirm Password do not match!")
            return redirect("admin_list")

        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' is already taken!")
            return redirect("admin_list")

        if User.objects.filter(email=email).exists():
            messages.error(request, f"An account with email '{email}' already exists!")
            return redirect("admin_list")

        new_admin = User.objects.create(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=make_password(password),
            is_superuser=is_superuser,
            is_staff=True,
            is_active=True,
        )
        messages.success(
            request, f"Administrator '{new_admin.username}' created successfully!"
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
        is_superuser = request.POST.get("is_superuser") == "1"

        if not (username and email):
            messages.error(request, "Username and email are required!")
            return redirect("admin_list")

        if username != target_admin.username and User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' is already in use!")
            return redirect("admin_list")

        if email != target_admin.email and User.objects.filter(email=email).exists():
            messages.error(request, f"Email '{email}' is already in use!")
            return redirect("admin_list")

        target_admin.username = username
        target_admin.email = email
        target_admin.first_name = first_name
        target_admin.last_name = last_name

        # Prevent demoting own superuser status if it's the last superuser
        if target_admin.id == user.id and not is_superuser:
            messages.error(request, "You cannot remove your own superuser status.")
        else:
            target_admin.is_superuser = is_superuser

        target_admin.is_staff = True

        if new_password:
            target_admin.password = make_password(new_password)

        target_admin.save()
        messages.success(request, f"Administrator '{target_admin.username}' updated successfully!")

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
    target_admin.delete()
    messages.success(request, f"Administrator '{username}' was deleted successfully.")
    return redirect("admin_list")
