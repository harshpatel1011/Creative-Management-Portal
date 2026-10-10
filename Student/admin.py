from django.contrib import admin
from .models import Student, StudentCourse, Project, ProjectFile, ProjectLink, Exam, ExamMarks

@admin.register(StudentCourse)
class StudentCourseAdmin(admin.ModelAdmin):
    list_display = ('student', 'course_name', 'created_at')
    search_fields = ('student__name', 'student__email', 'course_name')
    list_filter = ('course_name',)

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'course', 'created_at')
    search_fields = ('name', 'email', 'course')

class ProjectFileInline(admin.TabularInline):
    model = ProjectFile
    extra = 1

class ProjectLinkInline(admin.TabularInline):
    model = ProjectLink
    extra = 1

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'student', 'status', 'submitted_at')
    list_filter = ('status',)
    search_fields = ('title', 'student__name', 'student__email')
    inlines = [ProjectFileInline, ProjectLinkInline]

@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'exam_date', 'exam_time', 'total_marks', 'created_at')
    search_fields = ('title', 'subject')

@admin.register(ExamMarks)
class ExamMarksAdmin(admin.ModelAdmin):
    list_display = ('exam', 'student', 'marks_obtained', 'is_absent', 'grade', 'updated_at')
    list_filter = ('is_absent', 'grade', 'exam')
    search_fields = ('student__name', 'student__email', 'exam__title', 'exam__subject')
