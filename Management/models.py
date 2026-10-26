from django.db import models

class Admin(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    is_faculty = models.BooleanField(default=False)
    faculty_department = models.CharField(max_length=100, blank=True, default='')
    faculty_specialization = models.CharField(max_length=255, blank=True, default='')
    faculty_courses = models.TextField(blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')

    def __str__(self):
        role = " (Admin + Faculty)" if self.is_faculty else " (Admin)"
        return f"{self.name}{role}"
