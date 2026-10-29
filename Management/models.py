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

    def __str__(self):
        roles = []
        if self.is_faculty:
            roles.append("Faculty")
        if self.is_staff_role:
            roles.append("Staff")
        role_str = f" ({' + '.join(roles)})" if roles else " (Admin)"
        return f"{self.name}{role_str}"
