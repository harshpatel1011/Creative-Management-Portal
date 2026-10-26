from django.urls import path
from . import views

urlpatterns = [
    path('', views.student_dashboard_view, name='student_dashboard'),
    path('login/', views.student_login_view, name='student_login'),
    path('logout/', views.student_logout_view, name='student_logout'),
    path('projects/', views.student_projects_view, name='student_projects'),
    path('projects/add/', views.student_project_add_view, name='student_project_add'),
    path('projects/<int:project_id>/', views.student_project_detail_view, name='student_project_detail'),
    path('projects/<int:project_id>/edit/', views.student_project_edit_view, name='student_project_edit'),
    path('projects/<int:project_id>/delete/', views.student_project_delete_view, name='student_project_delete'),
    path('marks/', views.student_marks_view, name='student_marks'),
    path('attendance/', views.student_attendance_view, name='student_attendance'),
    path('daily-work/', views.student_daily_work_view, name='student_daily_work'),
    path('daily-work/submit/', views.student_daily_work_submit_view, name='student_daily_work_submit'),
    path('daily-work/<int:report_id>/edit/', views.student_daily_work_edit_view, name='student_daily_work_edit'),
    path('daily-work/<int:report_id>/delete/', views.student_daily_work_delete_view, name='student_daily_work_delete'),
    path('profile/', views.student_profile_view, name='student_profile'),
    path('change-password/', views.student_change_password_view, name='student_change_password'),
]
