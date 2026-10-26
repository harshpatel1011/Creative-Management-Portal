from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.db.models import Q
from django.utils import timezone
import datetime
import calendar
from .models import Student, Project, ProjectFile, ProjectLink, Exam, ExamMarks, Attendance, DailyWorkReport


def get_current_student(request):
    student_id = request.session.get("student_id")
    if student_id:
        return Student.objects.filter(id=student_id).first()
    return None


# --- STUDENT AUTH VIEWS ---


def student_login_view(request):
    user = get_current_student(request)
    if user:
        return redirect("student_dashboard")

    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        student = Student.objects.filter(email=email).first()

        if student:
            if check_password(password, student.password):
                request.session["student_id"] = student.id
                request.session["student_name"] = student.name
                request.session["student_email"] = student.email
                request.session["student_course"] = student.course
                messages.success(request, f"Welcome back, {student.name}!")
                return redirect("student_dashboard")
            else:
                messages.error(request, "Invalid password!")
        else:
            messages.error(request, "Invalid email or password!")

    return render(request, "student/login.html")


def student_logout_view(request):
    if "student_id" in request.session:
        del request.session["student_id"]
    request.session.flush()
    messages.success(request, "Successfully logged out!")
    return redirect("student_login")


# --- STUDENT PORTAL VIEWS ---


def student_dashboard_view(request):
    user = get_current_student(request)
    if not user:
        return redirect("student_login")

    projects = Project.objects.filter(student=user).prefetch_related("files", "links").order_by("-submitted_at")
    marks_records = ExamMarks.objects.filter(student=user).select_related("exam").order_by("-exam__exam_date")

    total_obtained = sum(m.marks_obtained for m in marks_records if m.marks_obtained is not None)
    total_possible = sum(m.exam.total_marks for m in marks_records if m.marks_obtained is not None)
    percentage = (
        round((float(total_obtained) / float(total_possible) * 100), 2)
        if total_possible > 0
        else 0
    )

    approved_count = projects.filter(status="Approved").count()
    submitted_count = projects.filter(status="Submitted").count()
    rejected_count = projects.filter(status="Rejected").count()

    graded_exams_count = marks_records.filter(Q(marks_obtained__isnull=False) | Q(is_absent=True)).count()
    pending_exams_count = marks_records.filter(marks_obtained__isnull=True, is_absent=False).count()

    context = {
        "user": user,
        "student": user,
        "projects": projects,
        "recent_projects": projects[:5],
        "marks_records": marks_records,
        "recent_marks": marks_records[:5],
        "total_projects": projects.count(),
        "approved_count": approved_count,
        "submitted_count": submitted_count,
        "rejected_count": rejected_count,
        "graded_exams_count": graded_exams_count,
        "pending_exams_count": pending_exams_count,
        "total_obtained": total_obtained,
        "total_possible": total_possible,
        "percentage": percentage,
        "attendance_stats": user.attendance_stats,
        "recent_attendance": user.attendance_records.all()[:5],
    }
    return render(request, "student/dashboard.html", context)


def student_projects_view(request):
    user = get_current_student(request)
    if not user:
        return redirect("student_login")

    projects = Project.objects.filter(student=user).prefetch_related("files", "links").order_by("-submitted_at")

    context = {
        "user": user,
        "student": user,
        "projects": projects,
        "total_count": projects.count(),
        "approved_count": projects.filter(status="Approved").count(),
        "submitted_count": projects.filter(status="Submitted").count(),
        "rejected_count": projects.filter(status="Rejected").count(),
    }
    return render(request, "student/projects.html", context)


def student_project_add_view(request):
    user = get_current_student(request)
    if not user:
        return redirect("student_login")

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        # Collect multiple files
        uploaded_files = request.FILES.getlist("project_files")
        if not uploaded_files and "project_file" in request.FILES:
            uploaded_files = [request.FILES["project_file"]]

        # Collect multiple links
        link_urls = request.POST.getlist("link_urls")
        link_labels = request.POST.getlist("link_labels")
        single_link = request.POST.get("project_link", "").strip()

        cleaned_links = []
        for i, url in enumerate(link_urls):
            u = url.strip()
            if u:
                lbl = link_labels[i].strip() if i < len(link_labels) else ""
                if not lbl:
                    if "github.com" in u.lower():
                        lbl = "GitHub Repo"
                    elif any(k in u.lower() for k in ["vercel.app", "netlify.app", "render.com", "herokuapp.com", "github.io"]):
                        lbl = "Live Demo"
                    elif "figma.com" in u.lower():
                        lbl = "Figma Design"
                    elif "drive.google" in u.lower():
                        lbl = "Google Drive"
                    else:
                        lbl = "Project Link"
                cleaned_links.append({"url": u, "label": lbl})

        if not cleaned_links and single_link:
            lbl = "GitHub Repo" if "github.com" in single_link.lower() else "Project Link"
            cleaned_links.append({"url": single_link, "label": lbl})

        primary_link = cleaned_links[0]["url"] if cleaned_links else ""

        if not title:
            messages.error(request, "Project title is required!")
            return render(
                request,
                "student/project_add.html",
                {
                    "user": user,
                    "student": user,
                    "title": title,
                    "cleaned_links": cleaned_links,
                    "description": description,
                },
            )

        if not uploaded_files and not cleaned_links:
            messages.error(
                request, "Please provide at least one: upload Project File(s) or add a Project Link!"
            )
            return render(
                request,
                "student/project_add.html",
                {
                    "user": user,
                    "student": user,
                    "title": title,
                    "cleaned_links": cleaned_links,
                    "description": description,
                },
            )

        primary_file = uploaded_files[0] if uploaded_files else None

        project = Project.objects.create(
            student=user,
            title=title,
            description=description,
            project_link=primary_link,
            project_file=primary_file,
            status="Submitted",
        )
        for f in uploaded_files:
            ProjectFile.objects.create(project=project, file=f)
        for item in cleaned_links:
            ProjectLink.objects.create(project=project, url=item["url"], label=item["label"])

        messages.success(request, f"Project '{title}' submitted successfully with {len(uploaded_files)} file(s) and {len(cleaned_links)} link(s)!")
        return redirect("student_projects")

    return render(request, "student/project_add.html", {"user": user, "student": user})


def student_project_detail_view(request, project_id):
    user = get_current_student(request)
    if not user:
        return redirect("student_login")

    project = Project.objects.filter(id=project_id, student=user).prefetch_related("files", "links").first()
    if not project:
        messages.error(request, "Project not found.")
        return redirect("student_projects")

    context = {
        "user": user,
        "student": user,
        "project": project,
    }
    return render(request, "student/project_detail.html", context)


def student_project_edit_view(request, project_id):
    user = get_current_student(request)
    if not user:
        return redirect("student_login")

    project = Project.objects.filter(id=project_id, student=user).prefetch_related("files", "links").first()
    if not project:
        messages.error(request, "Project not found.")
        return redirect("student_projects")

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        project.title = title
        project.description = description

        link_urls = request.POST.getlist("link_urls")
        link_labels = request.POST.getlist("link_labels")
        single_link = request.POST.get("project_link", "").strip()

        cleaned_links = []
        for i, url in enumerate(link_urls):
            u = url.strip()
            if u:
                lbl = link_labels[i].strip() if i < len(link_labels) else ""
                if not lbl:
                    if "github.com" in u.lower():
                        lbl = "GitHub Repo"
                    elif any(k in u.lower() for k in ["vercel.app", "netlify.app", "render.com", "herokuapp.com", "github.io"]):
                        lbl = "Live Demo"
                    elif "figma.com" in u.lower():
                        lbl = "Figma Design"
                    elif "drive.google" in u.lower():
                        lbl = "Google Drive"
                    else:
                        lbl = "Project Link"
                cleaned_links.append({"url": u, "label": lbl})

        if not cleaned_links and single_link:
            lbl = "GitHub Repo" if "github.com" in single_link.lower() else "Project Link"
            cleaned_links.append({"url": single_link, "label": lbl})

        if not title:
            messages.error(request, "Project title is required!")
            return render(
                request,
                "student/project_edit.html",
                {"user": user, "student": user, "project": project},
            )

        delete_file_ids = request.POST.getlist("delete_file_ids")
        remove_file = request.POST.get("remove_file") == "1"
        new_files = request.FILES.getlist("project_files")
        if not new_files and "project_file" in request.FILES:
            new_files = [request.FILES["project_file"]]

        # Calculate remaining existing files before performing deletion
        if remove_file:
            remaining_existing_count = 0
        else:
            remaining_existing_count = project.files.exclude(id__in=delete_file_ids).count()
            if remaining_existing_count == 0 and project.project_file and not project.files.exists():
                remaining_existing_count = 1

        total_files = remaining_existing_count + len(new_files)

        if total_files == 0 and not cleaned_links:
            messages.error(
                request, "Please provide at least one: keep/upload at least one Project File or enter at least one Project Link!"
            )
            return render(
                request,
                "student/project_edit.html",
                {"user": user, "student": user, "project": project},
            )

        # Update project fields
        project.title = title
        project.description = description
        primary_link = cleaned_links[0]["url"] if cleaned_links else ""
        project.project_link = primary_link

        # Delete removed files
        if delete_file_ids:
            for pf in project.files.filter(id__in=delete_file_ids):
                if pf.file:
                    pf.file.delete(save=False)
                pf.delete()

        if remove_file:
            if project.project_file:
                project.project_file.delete(save=False)
                project.project_file = None
            for pf in project.files.all():
                if pf.file:
                    pf.file.delete(save=False)
                pf.delete()

        # Add new uploaded files
        for f in new_files:
            ProjectFile.objects.create(project=project, file=f)

        # Sync primary project_file
        first_file = project.files.first()
        project.project_file = first_file.file if first_file else None

        project.status = "Submitted"
        project.submitted_at = timezone.now()
        project.save()

        # Sync ProjectLink records
        project.links.all().delete()
        for item in cleaned_links:
            ProjectLink.objects.create(project=project, url=item["url"], label=item["label"])

        messages.success(
            request, f"Project '{project.title}' updated successfully!"
        )
        return redirect("student_projects")

    return render(
        request,
        "student/project_edit.html",
        {"user": user, "student": user, "project": project},
    )


def student_project_delete_view(request, project_id):
    user = get_current_student(request)
    if not user:
        return redirect("student_login")

    project = Project.objects.filter(id=project_id, student=user).first()
    if not project:
        messages.error(request, "Project not found.")
        return redirect("student_projects")

    title = project.title
    if project.project_file:
        project.project_file.delete(save=False)
    project.delete()
    messages.success(request, f"Project '{title}' deleted successfully!")
    return redirect("student_projects")


def student_marks_view(request):
    user = get_current_student(request)
    if not user:
        return redirect("student_login")

    marks_records = ExamMarks.objects.filter(student=user).select_related("exam").order_by("-exam__exam_date")

    total_obtained = sum(m.marks_obtained for m in marks_records if m.marks_obtained is not None)
    total_possible = sum(m.exam.total_marks for m in marks_records if m.marks_obtained is not None)
    percentage = (
        round((float(total_obtained) / float(total_possible) * 100), 2)
        if total_possible > 0
        else 0
    )

    total_exams = marks_records.count()
    graded_records = [m for m in marks_records if m.marks_obtained is not None]
    graded_count = len(graded_records)
    absent_count = sum(1 for m in marks_records if m.is_absent or m.grade == "Absent")
    pending_count = sum(
        1 for m in marks_records if m.marks_obtained is None and not m.is_absent and m.grade != "Absent"
    )
    passed_count = sum(1 for m in graded_records if m.grade != "F")
    failed_count = sum(1 for m in graded_records if m.grade == "F") + absent_count

    overall_grade = "N/A"
    standing = "Awaiting Evaluation"
    if total_possible > 0:
        if percentage >= 90:
            overall_grade = "A+"
            standing = "Distinction with Honors"
        elif percentage >= 80:
            overall_grade = "A"
            standing = "First Class with Distinction"
        elif percentage >= 70:
            overall_grade = "B+"
            standing = "First Class"
        elif percentage >= 60:
            overall_grade = "B"
            standing = "Higher Second Class"
        elif percentage >= 50:
            overall_grade = "C"
            standing = "Second Class"
        elif percentage >= 33:
            overall_grade = "D"
            standing = "Pass Class"
        else:
            overall_grade = "F"
            standing = "Needs Improvement"

    # Distinct subjects for filter
    subjects = sorted(list(set(m.exam.subject for m in marks_records if m.exam and m.exam.subject)))

    context = {
        "user": user,
        "student": user,
        "marks_records": marks_records,
        "total_exams": total_exams,
        "graded_count": graded_count,
        "absent_count": absent_count,
        "pending_count": pending_count,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "total_obtained": total_obtained,
        "total_possible": total_possible,
        "percentage": percentage,
        "overall_grade": overall_grade,
        "standing": standing,
        "subjects": subjects,
    }
    return render(request, "student/marks.html", context)


def student_profile_view(request):
    user = get_current_student(request)
    if not user:
        return redirect("student_login")

    projects = Project.objects.filter(student=user)
    marks_records = ExamMarks.objects.filter(student=user)

    total_obtained = sum(m.marks_obtained for m in marks_records if m.marks_obtained is not None)
    total_possible = sum(m.exam.total_marks for m in marks_records if m.marks_obtained is not None)
    percentage = (
        round((float(total_obtained) / float(total_possible) * 100), 2)
        if total_possible > 0
        else 0
    )

    overall_grade = "N/A"
    standing = "Awaiting Evaluation"
    if total_possible > 0:
        if percentage >= 90:
            overall_grade = "A+"
            standing = "Distinction with Honors"
        elif percentage >= 80:
            overall_grade = "A"
            standing = "First Class with Distinction"
        elif percentage >= 70:
            overall_grade = "B+"
            standing = "First Class"
        elif percentage >= 60:
            overall_grade = "B"
            standing = "Higher Second Class"
        elif percentage >= 50:
            overall_grade = "C"
            standing = "Second Class"
        elif percentage >= 33:
            overall_grade = "D"
            standing = "Pass Class"
        else:
            overall_grade = "F"
            standing = "Needs Improvement"

    approved_projects_count = projects.filter(status="Approved").count()
    submitted_projects_count = projects.filter(status="Submitted").count()

    context = {
        "user": user,
        "student": user,
        "total_projects": projects.count(),
        "approved_projects_count": approved_projects_count,
        "submitted_projects_count": submitted_projects_count,
        "total_marks_records": marks_records.count(),
        "percentage": percentage,
        "overall_grade": overall_grade,
        "standing": standing,
        "attendance_stats": user.attendance_stats,
        "recent_attendance": user.attendance_records.all()[:5],
    }
    return render(request, "student/profile.html", context)


def student_change_password_view(request):
    user = get_current_student(request)
    if not user:
        return redirect("student_login")

    if request.method == "POST":
        current_password = request.POST.get("current_password")
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")

        if not (current_password and new_password and confirm_password):
            messages.error(request, "Please fill in all password fields!")
            return render(
                request,
                "student/change_password.html",
                {"user": user, "student": user},
            )

        if not check_password(current_password, user.password):
            messages.error(request, "Current password is incorrect!")
            return render(
                request,
                "student/change_password.html",
                {"user": user, "student": user},
            )

        if len(new_password) < 6:
            messages.error(request, "New password must be at least 6 characters long!")
            return render(
                request,
                "student/change_password.html",
                {"user": user, "student": user},
            )

        if new_password != confirm_password:
            messages.error(request, "New password and Confirm password do not match!")
            return render(
                request,
                "student/change_password.html",
                {"user": user, "student": user},
            )

        user.password = make_password(new_password)
        user.save()
        messages.success(request, "Your password has been changed successfully!")
        return redirect("student_profile")

    return render(
        request,
        "student/change_password.html",
        {"user": user, "student": user},
    )


# --- STUDENT ATTENDANCE PORTAL VIEW ---


def student_attendance_view(request):
    user = get_current_student(request)
    if not user:
        return redirect("student_login")

    today = datetime.date.today()
    try:
        month = int(request.GET.get("month", today.month))
        year = int(request.GET.get("year", today.year))
    except (ValueError, TypeError):
        month = today.month
        year = today.year

    month_name = calendar.month_name[month]
    _, num_days = calendar.monthrange(year, month)
    start_date = datetime.date(year, month, 1)
    end_date = datetime.date(year, month, num_days)

    # Monthly attendance records
    month_records = (
        user.attendance_records.filter(date__range=[start_date, end_date])
        .order_by("-date")
    )

    monthly_present = month_records.filter(status="Present").count()
    monthly_absent = month_records.filter(status="Absent").count()
    monthly_late = month_records.filter(status="Late").count()
    monthly_leave = month_records.filter(status="Leave").count()
    monthly_total = month_records.count()
    monthly_pct = (
        round(((monthly_present + monthly_late) / monthly_total) * 100, 1)
        if monthly_total > 0
        else 0
    )

    records_by_day = {r.date.day: r for r in month_records}
    calendar_days = []
    for d in range(1, num_days + 1):
        day_date = datetime.date(year, month, d)
        rec = records_by_day.get(d)
        calendar_days.append({
            "day": d,
            "weekday": day_date.strftime("%a"),
            "date": day_date,
            "status": rec.status if rec else None,
            "remarks": rec.remarks if rec else "",
            "time_slot": rec.time_slot if rec else user.class_time,
            "is_weekend": day_date.weekday() >= 6,
            "is_today": day_date == today,
        })

    all_time_stats = user.attendance_stats

    months_list = [(i, calendar.month_name[i]) for i in range(1, 13)]
    years_list = [year - 1, year, year + 1]

    context = {
        "user": user,
        "student": user,
        "month": month,
        "month_name": month_name,
        "year": year,
        "months_list": months_list,
        "years_list": years_list,
        "calendar_days": calendar_days,
        "month_records": month_records,
        "monthly_present": monthly_present,
        "monthly_absent": monthly_absent,
        "monthly_late": monthly_late,
        "monthly_leave": monthly_leave,
        "monthly_total": monthly_total,
        "monthly_pct": monthly_pct,
        "all_time_stats": all_time_stats,
    }
    return render(request, "student/attendance.html", context)

# --- DAILY WORK REPORT VIEWS ---


def student_daily_work_view(request):
    user = get_current_student(request)
    if not user:
        return redirect("student_login")

    today = datetime.date.today()
    course_filter = request.GET.get("course", "").strip()
    date_filter = request.GET.get("date", "").strip()

    reports_qs = DailyWorkReport.objects.filter(student=user)

    if course_filter:
        reports_qs = reports_qs.filter(course=course_filter)

    if date_filter:
        try:
            parsed_date = datetime.date.fromisoformat(date_filter)
            reports_qs = reports_qs.filter(date=parsed_date)
        except ValueError:
            pass

    reports = list(reports_qs.order_by("-date", "-created_at"))

    # Check today's submission status for student's enrolled courses
    courses = user.courses_list
    today_submissions = {
        r.course: r for r in DailyWorkReport.objects.filter(student=user, date=today)
    }

    course_status = []
    for c in courses:
        rep = today_submissions.get(c)
        course_status.append({
            "course": c,
            "has_submitted": rep is not None,
            "report": rep,
        })

    has_submitted_today = len(today_submissions) > 0

    context = {
        "user": user,
        "student": user,
        "reports": reports,
        "total_reports": len(reports),
        "courses": courses,
        "course_status": course_status,
        "today": today,
        "has_submitted_today": has_submitted_today,
        "course_filter": course_filter,
        "date_filter": date_filter,
    }
    return render(request, "student/daily_work.html", context)


def student_daily_work_submit_view(request):
    user = get_current_student(request)
    if not user:
        return redirect("student_login")

    courses = user.courses_list
    today = datetime.date.today()

    prefill_course = request.GET.get("course", "").strip()
    if not prefill_course and courses:
        prefill_course = courses[0]

    student_batches = user.batches_list or ([user.class_time] if user.class_time else [])
    default_batch_time = student_batches[0] if student_batches else (user.class_time or "")

    if request.method == "POST":
        course = request.POST.get("course", "").strip()
        date_str = request.POST.get("date", "").strip()
        running_topic = request.POST.get("running_topic", "").strip()
        lecture_status = request.POST.get("lecture_status", "lecture").strip()
        class_work = request.POST.get("class_work", "").strip()
        class_work_time = request.POST.get("class_work_time", "").strip()
        home_work = request.POST.get("home_work", "").strip()
        home_work_time = request.POST.get("home_work_time", "").strip()

        try:
            report_date = datetime.date.fromisoformat(date_str) if date_str else today
        except ValueError:
            report_date = today

        if report_date < today:
            messages.error(request, "Daily work reports cannot be submitted for past dates. Work reports must be submitted on the day of work.")
            return redirect("student_daily_work")

        if not class_work_time and default_batch_time:
            class_work_time = default_batch_time

        if not (course and running_topic and class_work and home_work):
            messages.error(request, "Please fill in all required fields: Course, Running Topic, Class Work, and Home Practice Work!")
            return render(request, "student/daily_work_form.html", {
                "user": user,
                "student": user,
                "courses": courses,
                "selected_course": course,
                "report_date": report_date.isoformat(),
                "running_topic": running_topic,
                "lecture_status": lecture_status,
                "class_work": class_work,
                "class_work_time": class_work_time,
                "home_work": home_work,
                "home_work_time": home_work_time,
                "student_batches": student_batches,
                "default_batch_time": default_batch_time,
                "class_time_choices": [c[0] for c in Student.CLASS_TIME_CHOICES],
            })

        # Save or update report for (student, date, course)
        report, created = DailyWorkReport.objects.update_or_create(
            student=user,
            date=report_date,
            course=course,
            defaults={
                "running_topic": running_topic,
                "lecture_status": lecture_status,
                "class_work": class_work,
                "class_work_time": class_work_time,
                "home_work": home_work,
                "home_work_time": home_work_time,
            }
        )

        action_msg = "submitted" if created else "updated"
        messages.success(request, f"Daily work report for '{course}' on {report_date.strftime('%b %d, %Y')} {action_msg} successfully!")
        return redirect("student_daily_work")

    return render(request, "student/daily_work_form.html", {
        "user": user,
        "student": user,
        "courses": courses,
        "selected_course": prefill_course,
        "report_date": today.isoformat(),
        "today": today,
        "student_batches": student_batches,
        "default_batch_time": default_batch_time,
        "class_time_choices": [c[0] for c in Student.CLASS_TIME_CHOICES],
    })


def student_daily_work_edit_view(request, report_id):
    user = get_current_student(request)
    if not user:
        return redirect("student_login")

    report = DailyWorkReport.objects.filter(id=report_id, student=user).first()
    if not report:
        messages.error(request, "Daily work report not found.")
        return redirect("student_daily_work")

    today = datetime.date.today()
    if report.is_locked:
        messages.error(request, f"This daily work report from {report.date.strftime('%b %d, %Y')} cannot be edited because the date has passed. Reports can only be edited on the day of submission.")
        return redirect("student_daily_work")

    courses = user.courses_list
    student_batches = user.batches_list or ([user.class_time] if user.class_time else [])
    default_batch_time = student_batches[0] if student_batches else (user.class_time or "")

    if request.method == "POST":
        if report.is_locked:
            messages.error(request, "This report cannot be edited after its date has passed.")
            return redirect("student_daily_work")
        course = request.POST.get("course", "").strip()
        date_str = request.POST.get("date", "").strip()
        running_topic = request.POST.get("running_topic", "").strip()
        lecture_status = request.POST.get("lecture_status", "lecture").strip()
        class_work = request.POST.get("class_work", "").strip()
        class_work_time = request.POST.get("class_work_time", "").strip()
        home_work = request.POST.get("home_work", "").strip()
        home_work_time = request.POST.get("home_work_time", "").strip()

        try:
            report_date = datetime.date.fromisoformat(date_str) if date_str else report.date
        except ValueError:
            report_date = report.date

        if not (course and running_topic and class_work and home_work):
            messages.error(request, "Please fill in all required fields!")
            return render(request, "student/daily_work_form.html", {
                "user": user,
                "student": user,
                "report": report,
                "courses": courses,
                "student_batches": student_batches,
                "default_batch_time": default_batch_time,
                "class_time_choices": [c[0] for c in Student.CLASS_TIME_CHOICES],
            })

        report.course = course
        report.date = report_date
        report.running_topic = running_topic
        report.lecture_status = lecture_status
        report.class_work = class_work
        report.class_work_time = class_work_time
        report.home_work = home_work
        report.home_work_time = home_work_time
        report.save()

        messages.success(request, f"Daily work report updated successfully!")
        return redirect("student_daily_work")

    return render(request, "student/daily_work_form.html", {
        "user": user,
        "student": user,
        "report": report,
        "courses": courses,
        "selected_course": report.course,
        "report_date": report.date.isoformat(),
        "student_batches": student_batches,
        "default_batch_time": default_batch_time,
        "class_time_choices": [c[0] for c in Student.CLASS_TIME_CHOICES],
    })


def student_daily_work_delete_view(request, report_id):
    user = get_current_student(request)
    if not user:
        return redirect("student_login")

    report = DailyWorkReport.objects.filter(id=report_id, student=user).first()
    if not report:
        messages.error(request, "Daily work report not found.")
        return redirect("student_daily_work")

    if report.is_locked:
        messages.error(request, f"This daily work report from {report.date.strftime('%b %d, %Y')} cannot be deleted because the date has passed.")
        return redirect("student_daily_work")

    course = report.course
    date_str = report.date.strftime("%b %d, %Y")
    report.delete()
    messages.success(request, f"Daily work report for '{course}' ({date_str}) deleted successfully.")
    return redirect("student_daily_work")
