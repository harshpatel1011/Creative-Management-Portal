from django.db import models

class Admin(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    is_faculty = models.BooleanField(default=False)
    is_staff_role = models.BooleanField(default=False)
    faculty_department = models.CharField(max_length=100, blank=True, default='')
    faculty_specialization = models.CharField(max_length=255, blank=True, default='')
    faculty_courses = models.TextField(blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    pending_faculty_courses = models.TextField(blank=True, default='')
    course_request_status = models.CharField(max_length=20, blank=True, default='')
    course_request_date = models.DateTimeField(null=True, blank=True)

    @property
    def pending_courses_list(self):
        if self.pending_faculty_courses:
            return [c.strip() for c in self.pending_faculty_courses.split(',') if c.strip()]
        return []

    @property
    def has_pending_course_request(self):
        return self.course_request_status == 'Pending' and bool(self.pending_faculty_courses.strip())

    def __str__(self):
        roles = []
        if self.is_faculty:
            roles.append("Faculty")
        if self.is_staff_role:
            roles.append("Staff")
        role_str = f" ({' + '.join(roles)})" if roles else " (Admin)"
        return f"{self.name}{role_str}"
