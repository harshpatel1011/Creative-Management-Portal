import datetime
import os
from django.db import models

class Faculty(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField(max_length=150, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, default='')
    specialization = models.CharField(max_length=255, blank=True, default='')
    courses = models.TextField(blank=True, default='')
    is_admin = models.BooleanField(default=False)
    admin_account = models.ForeignKey('Management.Admin', on_delete=models.SET_NULL, null=True, blank=True, related_name='faculty_profiles')
    created_by = models.CharField(max_length=100, blank=True, default='Admin')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    password = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Faculties'

    def __str__(self):
        return self.name


    @property
    def courses_list(self):
        if self.courses:
            return [c.strip() for c in self.courses.split(',') if c.strip()]
        return []


class Student(models.Model):
    CLASS_TIME_CHOICES = [
        ('08:00 am to 10:00 am', '08:00 am to 10:00 am'),
        ('10:00 am to 12:00 pm', '10:00 am to 12:00 pm'),
        ('12:00 pm to 02:00 pm', '12:00 pm to 02:00 pm'),
        ('02:00 pm to 04:00 pm', '02:00 pm to 04:00 pm'),
        ('04:00 pm to 06:00 pm', '04:00 pm to 06:00 pm'),
        ('06:00 pm to 08:00 pm', '06:00 pm to 08:00 pm'),
    ]

    COURSE_CATEGORIES = {
        'Development Courses': [
            'Master In Flutter Development',
            'Master In Android Development',
            'Master In Game Development',
            'Master In Full Stack Development',
            'Master In Web Development',
            'Master In React Native',
            'Master In Data Science',
            'Master In ASP.net development',
            'Master In Data Analytics',
            'Master in Software Testing',
        ],
        'Design Courses': [
            'Master In Web Design',
            'Master in UI/UX Design',
            'Master In 2D/3D Animation',
            'Master In 2D Animation',
            'Master In 3D Animation',
            'Advance Graphics Design + AI',
            'Video Editing + AI',
            '2D/3D Game Design',
            'Maya Pro | 3Ds Max Pro',
            'Blender 3D Design',
        ],
        'Programming IT': [
            'C Programming',
            'Node JS',
            'C++ Programming',
            'Java Programming',
            'IOS',
            'Advance PHP',
            'Laravel',
            'Wordpress',
            'CodeIgniter',
        ],
        'Trendy Courses': [
            'Advance Finance Management',
            'Angular JS',
            'React JS',
            'Ethical Hacking',
            'Unity 3D',
            'Python',
            'React Native',
            'Desktop App Development',
            'Java Spring Boot',
        ],
        'Civil-Mech. Engineering': [
            'AutoCAD Civil',
            '3Ds Max',
            'Google SketchUp',
            'Lumion',
            'Revit Architecture',
            'Interior & Exterior Design',
            'AutoCAD Mechanical',
            'SolidWorks',
            'Creo Parametrics 2.0',
        ],
        'Business Development': [
            'Master in Business Management',
            'Digital Marketing + AI',
            'Corporate English',
            'Social Media Marketing',
            'Business Marketing',
            'Business Administration',
        ],
        'Short Term Courses': [
            'Adobe Illustrator',
            'Master in E-Commerce',
            'Digital Print',
            'Hotfix Design',
            'Accounting WITH Tally Prime',
            'CCC- Basic Computer Course',
            'Photoshop',
            'CorelDraw',
        ],
        'Diploma Courses': [
            'Diploma In Web Design',
            'Diploma In Web Development',
        ],
    }

    STUDENT_STATUS_CHOICES = [
        ('Running', 'Running'),
        ('Completed', 'Completed'),
        ('Dropped', 'Dropped'),
        ('On Leave', 'On Leave'),
        ('Suspend', 'Suspend'),
        ('In Job', 'In Job'),
        ('In Project', 'In Project'),
        ('Branch Transfer', 'Branch Transfer'),
    ]

    name = models.CharField(max_length=100)
    email = models.EmailField(max_length=100, unique=True)
    password = models.CharField(max_length=255)
    course = models.CharField(max_length=255, blank=True, default='')
    class_time = models.CharField(max_length=255, blank=True, null=True)
    assigned_batch = models.ForeignKey('Batch', on_delete=models.SET_NULL, null=True, blank=True, related_name='enrolled_students')
    faculty = models.CharField(max_length=255, blank=True, default='')
    faculty_member = models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    phone = models.CharField(max_length=20, blank=True, null=True)
    status = models.CharField(max_length=50, choices=STUDENT_STATUS_CHOICES, default='Running')
    is_on_leave = models.BooleanField(default=False)
    leave_reason = models.CharField(max_length=255, blank=True, default='')
    leave_start_date = models.DateField(null=True, blank=True)
    leave_end_date = models.DateField(null=True, blank=True)
    REFERENCE_CHOICES = [
        ('Internet', 'Internet'),
        ('Student', 'Student'),
        ('Seminar', 'Seminar'),
        ('Staff', 'Staff'),
        ('Other', 'Other'),
    ]
    reference = models.CharField(max_length=50, choices=REFERENCE_CHOICES, blank=True, default='')
    reference_detail = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def courses_list(self):
        enrolled = list(self.enrolled_courses.values_list('course_name', flat=True))
        if enrolled:
            return enrolled
        if self.course:
            return [c.strip() for c in self.course.split(',') if c.strip()]
        return []

    @property
    def batches_list(self):
        enrolled = list(self.enrolled_batches.values_list('batch_time', flat=True))
        if enrolled:
            return enrolled
        if self.class_time:
            return [b.strip() for b in self.class_time.split(',') if b.strip()]
        return []

    @property
    def batch_display(self):
        if self.assigned_batch:
            return self.assigned_batch.name
        first_b = self.assigned_batches.first()
        if first_b:
            return first_b.name
        return "Not Assigned"

    @property
    def is_batch_assigned(self):
        return bool(self.assigned_batch or self.assigned_batches.exists())

    @property
    def reference_display(self):
        if not self.reference:
            return "Not Specified"
        if self.reference_detail:
            return f"{self.reference} ({self.reference_detail})"
        return self.reference

    @property
    def whatsapp_number(self):
        if not self.phone:
            return ""
        digits = "".join(ch for ch in str(self.phone) if ch.isdigit())
        if len(digits) == 10:
            return f"91{digits}"
        return digits

    @property
    def whatsapp_url(self):
        num = self.whatsapp_number
        if num:
            return f"https://wa.me/{num}"
        return ""

    @property
    def faculty_display(self):
        if self.faculty_member:
            return self.faculty_member.name
        if self.faculty:
            return self.faculty
        return "Not Assigned"

    @property
    def attendance_stats(self):
        records = self.attendance_records.all()
        total = records.count()
        if total == 0:
            return {
                "total": 0, "present": 0, "absent": 0, "late": 0, "leave": 0,
                "percentage": 0, "status": "No Records"
            }
        present = records.filter(status="Present").count()
        absent = records.filter(status="Absent").count()
        late = records.filter(status="Late").count()
        leave = records.filter(status="Leave").count()
        attended = present + late
        percentage = round((attended / total) * 100, 1) if total > 0 else 0
        if percentage >= 85:
            status = "Excellent"
        elif percentage >= 75:
            status = "Good"
        elif percentage >= 60:
            status = "Average"
        else:
            status = "Low Attendance"
        return {
            "total": total,
            "present": present,
            "absent": absent,
            "late": late,
            "leave": leave,
            "percentage": percentage,
            "status": status
        }

    @property
    def is_currently_on_leave(self):
        today = datetime.date.today()
        if not self.is_on_leave:
            return False
        if self.leave_end_date and self.leave_end_date < today:
            return False
        return True

    def is_on_leave_on(self, target_date=None):
        if target_date is None:
            target_date = datetime.date.today()
        if isinstance(target_date, str):
            try:
                target_date = datetime.date.fromisoformat(target_date)
            except ValueError:
                return False

        if not self.is_on_leave and not (self.leave_start_date and self.leave_end_date):
            return False

        start_ok = (self.leave_start_date is None) or (self.leave_start_date <= target_date)
        end_ok = (self.leave_end_date is None) or (target_date <= self.leave_end_date)
        return start_ok and end_ok

    @property
    def status_display(self):
        return self.status or ("On Leave" if self.is_on_leave else "Running")

    def save(self, *args, **kwargs):
        today = datetime.date.today()
        # Automatically clear expired leave upon save
        if self.leave_end_date and self.leave_end_date < today:
            if self.status == "On Leave":
                self.status = "Running"
            self.is_on_leave = False
            self.leave_reason = ""
            self.leave_start_date = None
            self.leave_end_date = None
        super().save(*args, **kwargs)

    @classmethod
    def sync_expired_leaves(cls):
        """
        Automatically expires any leaves where leave_end_date < today.
        Sets is_on_leave = False and status = 'Running'.
        Also activates scheduled leaves whose start date has arrived.
        """
        from django.db.models import Q
        today = datetime.date.today()

        # 1. Expire past leaves
        expired = cls.objects.filter(
            is_on_leave=True,
            leave_end_date__isnull=False,
            leave_end_date__lt=today
        )
        if expired.exists():
            expired.update(
                status="Running",
                is_on_leave=False,
                leave_reason="",
                leave_start_date=None,
                leave_end_date=None,
            )

        # 2. Activate scheduled leaves where leave_start_date has arrived and leave hasn't ended
        to_activate = cls.objects.filter(
            is_on_leave=False,
            leave_start_date__isnull=False,
            leave_start_date__lte=today
        ).filter(
            Q(leave_end_date__isnull=True) | Q(leave_end_date__gte=today)
        )
        if to_activate.exists():
            to_activate.update(is_on_leave=True, status="On Leave")

    def __str__(self):
        return f"{self.name} ({self.email})"


class Batch(models.Model):
    name = models.CharField(max_length=150, help_text="Batch Identifier, e.g. WD-10AM or Python Morning A")
    course = models.CharField(max_length=150, blank=True, default='', help_text="Field of study / Course")
    time_slot = models.CharField(max_length=100, choices=Student.CLASS_TIME_CHOICES, help_text="Scheduled Time Slot")
    faculty = models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_batches')
    students = models.ManyToManyField(Student, blank=True, related_name='assigned_batches')
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['time_slot', 'name']
        verbose_name_plural = 'Batches'

    def __str__(self):
        fac = f" ({self.faculty.name})" if self.faculty else ""
        return f"{self.name} - {self.time_slot}{fac}"

    @property
    def student_count(self):
        return self.students.count()

    @property
    def active_exam_students(self):
        """Returns students belonging to this batch eligible for exams (excludes Dropped, On Leave, Suspend)."""
        from django.db.models import Q
        return Student.objects.filter(
            Q(assigned_batch=self) | Q(assigned_batches=self)
        ).exclude(
            status__in=['Dropped', 'On Leave', 'Suspend']
        ).exclude(
            is_on_leave=True
        ).distinct()

    @property
    def active_exam_students_count(self):
        return self.active_exam_students.count()

    @property
    def faculty_display(self):
        return self.faculty.name if self.faculty else "Unassigned Faculty"

    @property
    def batch_number(self):
        clean = (self.name or "").strip()
        if clean.lower().startswith('batch'):
            rest = clean[5:].strip().lstrip('#').strip()
            if rest:
                return rest
        if clean:
            return clean
        return str(self.id) if self.id else ""


class StudentBatch(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrolled_batches')
    batch_time = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'batch_time')
        ordering = ['created_at']

    def __str__(self):
        return f"{self.student.name} - {self.batch_time}"


class StudentCourse(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrolled_courses')
    course_name = models.CharField(max_length=150)
    faculty = models.CharField(max_length=150, blank=True, default='')
    faculty_member = models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'course_name')
        ordering = ['created_at']

    def __str__(self):
        return f"{self.student.name} - {self.course_name}"


class Project(models.Model):
    STATUS_CHOICES = [
        ('Submitted', 'Submitted'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='projects')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    project_link = models.URLField(blank=True, null=True)
    project_file = models.FileField(upload_to='project_files/', blank=True, null=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Submitted')
    submitted_at = models.DateTimeField(auto_now_add=True)

    @property
    def filename(self):
        if self.project_file:
            return os.path.basename(self.project_file.name)
        return ""

    @property
    def file_extension(self):
        if self.project_file:
            _, ext = os.path.splitext(self.project_file.name)
            return ext.lstrip('.').upper()
        return ""

    @property
    def file_size_formatted(self):
        if self.project_file and hasattr(self.project_file, 'size'):
            try:
                size_bytes = self.project_file.size
                if size_bytes < 1024:
                    return f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    return f"{round(size_bytes / 1024, 1)} KB"
                else:
                    return f"{round(size_bytes / (1024 * 1024), 2)} MB"
            except Exception:
                return ""
        return ""

    @property
    def all_files(self):
        files_qs = list(self.files.all())
        if files_qs:
            return files_qs
        if self.project_file:
            class DummyFile:
                def __init__(self, file_field):
                    self.file = file_field
                @property
                def url(self):
                    return self.file.url if hasattr(self.file, 'url') else ''
                @property
                def filename(self):
                    return os.path.basename(self.file.name) if self.file else ''
                @property
                def file_extension(self):
                    if self.file:
                        _, ext = os.path.splitext(self.file.name)
                        return ext.lstrip('.').upper()
                    return ''
                @property
                def file_size_formatted(self):
                    if self.file and hasattr(self.file, 'size'):
                        try:
                            size_bytes = self.file.size
                            if size_bytes < 1024:
                                return f"{size_bytes} B"
                            elif size_bytes < 1024 * 1024:
                                return f"{round(size_bytes / 1024, 1)} KB"
                            else:
                                return f"{round(size_bytes / (1024 * 1024), 2)} MB"
                        except Exception:
                            return ""
                    return ""
            return [DummyFile(self.project_file)]
        return []

    @property
    def all_links(self):
        links_qs = list(self.links.all())
        if links_qs:
            return links_qs
        if self.project_link:
            class DummyLink:
                def __init__(self, url):
                    self.url = url
                    self.label = 'GitHub Repo' if 'github.com' in url.lower() else 'Project Link'
                @property
                def display_label(self):
                    return self.label
                @property
                def icon_class(self):
                    combined = f"{self.label} {self.url}".lower()
                    if 'github' in combined:
                        return 'fa-brands fa-github'
                    if 'gitlab' in combined:
                        return 'fa-brands fa-gitlab'
                    if 'figma' in combined:
                        return 'fa-brands fa-figma'
                    if 'drive' in combined:
                        return 'fa-brands fa-google-drive'
                    if 'live' in combined or 'demo' in combined:
                        return 'fa-solid fa-globe'
                    return 'fa-solid fa-link'
            return [DummyLink(self.project_link)]
        return []

    def __str__(self):
        return f"{self.title} ({self.student.name})"


class ProjectFile(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to='project_files/')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def filename(self):
        if self.file:
            return os.path.basename(self.file.name)
        return ""

    @property
    def file_extension(self):
        if self.file:
            _, ext = os.path.splitext(self.file.name)
            return ext.lstrip('.').upper()
        return ""

    @property
    def file_size_formatted(self):
        if self.file and hasattr(self.file, 'size'):
            try:
                size_bytes = self.file.size
                if size_bytes < 1024:
                    return f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    return f"{round(size_bytes / 1024, 1)} KB"
                else:
                    return f"{round(size_bytes / (1024 * 1024), 2)} MB"
            except Exception:
                return ""
        return ""

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.project.title} - {self.filename}"


class ProjectLink(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='links')
    url = models.URLField(max_length=500)
    label = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def display_label(self):
        if self.label and self.label.strip():
            return self.label.strip()
        url_lower = self.url.lower()
        if 'github.com' in url_lower:
            return 'GitHub'
        elif 'gitlab.com' in url_lower:
            return 'GitLab'
        elif 'figma.com' in url_lower:
            return 'Figma'
        elif 'drive.google.com' in url_lower:
            return 'Drive'
        elif 'youtube.com' in url_lower or 'youtu.be' in url_lower:
            return 'Video'
        return 'Link'

    @property
    def icon_class(self):
        combined = f"{self.label} {self.url}".lower()
        if 'github' in combined:
            return 'fa-brands fa-github'
        if 'gitlab' in combined:
            return 'fa-brands fa-gitlab'
        if 'figma' in combined:
            return 'fa-brands fa-figma'
        if 'drive' in combined:
            return 'fa-brands fa-google-drive'
        if 'youtube' in combined or 'video' in combined:
            return 'fa-brands fa-youtube'
        if 'live' in combined or 'demo' in combined or 'website' in combined or 'app' in combined:
            return 'fa-solid fa-globe'
        return 'fa-solid fa-link'

    def __str__(self):
        return f"{self.display_label}: {self.url}"

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.label}: {self.url}" if self.label else self.url


class Exam(models.Model):
    title = models.CharField(max_length=200)
    subject = models.CharField(max_length=100)
    exam_date = models.DateField()
    exam_time = models.CharField(max_length=50, blank=True, null=True)
    total_marks = models.DecimalField(max_digits=5, decimal_places=2, default=100.00)
    batches = models.ManyToManyField(Batch, blank=True, related_name='exams')
    students = models.ManyToManyField(Student, related_name='exams', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        time_str = f" at {self.exam_time}" if self.exam_time else ""
        return f"{self.title} - {self.subject} ({self.exam_date}{time_str})"

    @property
    def batches_display(self):
        batch_list = list(self.batches.all())
        if batch_list:
            return ", ".join([b.name for b in batch_list])
        student_batches = set()
        for s in self.students.all():
            if s.assigned_batch:
                student_batches.add(s.assigned_batch.name)
            for b in s.assigned_batches.all():
                student_batches.add(b.name)
        if student_batches:
            return ", ".join(sorted(student_batches))
        return "All / Unassigned"

    @property
    def batch_names_list(self):
        names = [b.name for b in self.batches.all()]
        if not names:
            for s in self.students.all():
                if s.assigned_batch and s.assigned_batch.name not in names:
                    names.append(s.assigned_batch.name)
                for b in s.assigned_batches.all():
                    if b.name not in names:
                        names.append(b.name)
        return names


class ExamMarks(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='marks_records')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='exam_marks')
    marks_obtained = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_absent = models.BooleanField(default=False)
    grade = models.CharField(max_length=10, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('exam', 'student')

    def save(self, *args, **kwargs):
        if self.is_absent:
            self.marks_obtained = None
            self.grade = 'Absent'
        elif self.marks_obtained is not None and self.exam.total_marks and self.exam.total_marks > 0:
            percentage = (float(self.marks_obtained) / float(self.exam.total_marks)) * 100
            if percentage >= 90:
                self.grade = 'A+'
            elif percentage >= 80:
                self.grade = 'A'
            elif percentage >= 70:
                self.grade = 'B+'
            elif percentage >= 60:
                self.grade = 'B'
            elif percentage >= 50:
                self.grade = 'C'
            elif percentage >= 33:
                self.grade = 'D'
            else:
                self.grade = 'F'
        elif self.marks_obtained is None:
            self.grade = None
        super().save(*args, **kwargs)

    @property
    def percentage(self):
        if self.marks_obtained is not None and self.exam and self.exam.total_marks and self.exam.total_marks > 0:
            return round((float(self.marks_obtained) / float(self.exam.total_marks)) * 100, 1)
        return None

    def __str__(self):
        return f"{self.student.name} - {self.exam.title}: {self.marks_obtained}/{self.exam.total_marks}"

class Attendance(models.Model):
    STATUS_CHOICES = [
        ("Present", "Present"),
        ("Absent", "Absent"),
        ("Late", "Late"),
        ("Leave", "Leave"),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance_records")
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Present")
    time_slot = models.CharField(max_length=50, choices=Student.CLASS_TIME_CHOICES, blank=True, null=True)
    remarks = models.CharField(max_length=255, blank=True, default="")
    marked_by = models.CharField(max_length=100, blank=True, default="Admin")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("student", "date")
        ordering = ["-date", "student__name"]

    def __str__(self):
        return f"{self.student.name} - {self.date}: {self.status}"


class DailyWorkReport(models.Model):
    LECTURE_CHOICES = [
        ('lecture', 'Lecture Conducted'),
        ('no_lecture', 'No Lecture Today (Class Lab / Practical Work)'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='daily_reports')
    date = models.DateField(default=datetime.date.today)
    course = models.CharField(max_length=150)
    running_topic = models.CharField(max_length=255)
    lecture_status = models.CharField(max_length=50, choices=LECTURE_CHOICES, default='lecture')
    class_work = models.TextField(help_text="Lecture topic taught or class practical work if no lecture")
    class_work_time = models.CharField(max_length=100, blank=True, default="", help_text="Timing or duration of class work, e.g. 10:00 am to 12:00 pm or 2 hours")
    home_work = models.TextField(help_text="Home practice work / self-study assignment completed")
    home_work_time = models.CharField(max_length=100, blank=True, default="", help_text="Timing or duration of home practice work, e.g. 07:00 pm to 09:00 pm or 1.5 hours")
    faculty = models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True, blank=True, related_name='daily_reports')
    admin_remarks = models.TextField(blank=True, default='')
    reviewed_by = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'date', 'course')
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.student.name} - {self.date} - {self.course}: {self.running_topic}"

    @property
    def is_lecture(self):
        return self.lecture_status == 'lecture'

    @property
    def is_locked(self):
        return self.date < datetime.date.today()

    @property
    def can_edit(self):
        return self.date >= datetime.date.today()
