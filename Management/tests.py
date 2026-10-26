from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
import datetime
from Student.models import Student, Project, Exam, ExamMarks, ProjectFile, ProjectLink, Attendance

class StudentManagementSystemTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Seed 2 Admins using create_superuser
        self.admin1 = User.objects.create_superuser(
            username="admin1",
            email="admin1@creative.com",
            password="admin123"
        )
        self.admin2 = User.objects.create_superuser(
            username="admin2",
            email="admin2@creative.com",
            password="admin123"
        )

    def test_two_admins_exist_and_passwords_hashed(self):
        self.assertEqual(User.objects.filter(is_superuser=True).count(), 2)
        self.assertTrue(check_password("admin123", self.admin1.password))
        self.assertTrue(check_password("admin123", self.admin2.password))
        self.assertFalse(check_password("wrongpass", self.admin1.password))

    def test_admin_login_and_session(self):
        response = self.client.post(reverse('admin_login'), {
            'email': 'admin1@creative.com',
            'password': 'admin123'
        })
        self.assertRedirects(response, reverse('admin_dashboard'))
        session = self.client.session
        self.assertEqual(session.get('admin_id'), self.admin1.id)
        self.assertEqual(session.get('admin_email'), 'admin1@creative.com')

    def test_admin_registers_student_with_hashed_password(self):
        # Login as Admin 1
        self.client.post(reverse('admin_login'), {
            'email': 'admin1@creative.com',
            'password': 'admin123'
        })

        # Register Student
        response = self.client.post(reverse('admin_student_register'), {
            'name': 'John Doe',
            'email': 'johndoe@example.com',
            'password': 'studentpass123',
            'course': 'Computer Science',
            'phone': '1234567890',
        })
        self.assertRedirects(response, reverse('admin_student_list'))

        student = Student.objects.get(email='johndoe@example.com')
        self.assertEqual(student.name, 'John Doe')
        self.assertTrue(check_password('studentpass123', student.password))

    def test_student_login_and_project_submission(self):
        # Create student directly with make_password
        student = Student.objects.create(
            name='Jane Smith',
            email='jane@example.com',
            password=make_password('mypassword'),
            course='Artificial Intelligence'
        )

        # Student logs in
        login_resp = self.client.post(reverse('student_login'), {
            'email': 'jane@example.com',
            'password': 'mypassword'
        })
        self.assertRedirects(login_resp, reverse('student_dashboard'))
        self.assertEqual(self.client.session.get('student_id'), student.id)

        # Student submits project
        proj_resp = self.client.post(reverse('student_project_add'), {
            'title': 'AI Chatbot',
            'description': 'A smart NLP assistant',
            'project_link': 'https://github.com/janesmith/chatbot'
        })
        self.assertRedirects(proj_resp, reverse('student_projects'))
        self.assertTrue(Project.objects.filter(student=student, title='AI Chatbot').exists())

    def test_admin_creates_exam_selects_student_and_adds_marks(self):
        # Login as Admin 2
        self.client.post(reverse('admin_login'), {
            'email': 'admin2@creative.com',
            'password': 'admin123'
        })

        student1 = Student.objects.create(
            name='Mark Davis',
            email='mark@example.com',
            password=make_password('pass123'),
            course='Data Science'
        )
        student2 = Student.objects.create(
            name='Sara Connor',
            email='sara@example.com',
            password=make_password('pass123'),
            course='AI & Robotics'
        )

        # 1. Admin creates Exam and assigns students
        create_resp = self.client.post(reverse('admin_exam_create'), {
            'title': 'Midterm Python Exam',
            'subject': 'Python Programming',
            'exam_date': '2026-05-15',
            'total_marks': '100',
            'student_ids': [student1.id, student2.id]
        })
        exam = Exam.objects.get(title='Midterm Python Exam')
        self.assertRedirects(create_resp, reverse('admin_exam_detail', kwargs={'exam_id': exam.id}))
        self.assertEqual(exam.students.count(), 2)

        # 2. Admin views Exam Card & evaluation table
        card_resp = self.client.get(reverse('admin_exam_detail', kwargs={'exam_id': exam.id}))
        self.assertEqual(card_resp.status_code, 200)
        self.assertContains(card_resp, 'Midterm Python Exam')
        self.assertContains(card_resp, 'Mark Davis')
        self.assertContains(card_resp, 'Sara Connor')

        # 3. Admin enters marks for student1 from the Exam Card
        save_marks_resp = self.client.post(reverse('admin_exam_marks_save', kwargs={'exam_id': exam.id}), {
            'student_id': student1.id,
            'marks_obtained': '92'
        })
        self.assertRedirects(save_marks_resp, reverse('admin_exam_detail', kwargs={'exam_id': exam.id}))

        mark_rec = ExamMarks.objects.get(exam=exam, student=student1)
        self.assertEqual(mark_rec.marks_obtained, 92)
        self.assertEqual(mark_rec.grade, 'A+')

        # 4. Student views their Exam and Grade
        self.client.post(reverse('student_login'), {
            'email': 'mark@example.com',
            'password': 'pass123'
        })
        student_marks_resp = self.client.get(reverse('student_marks'))
        self.assertEqual(student_marks_resp.status_code, 200)
        self.assertContains(student_marks_resp, 'Midterm Python Exam')
        self.assertContains(student_marks_resp, '92')
        self.assertContains(student_marks_resp, 'A+')

    def test_admin_shows_user_projects_and_updates_status(self):
        student = Student.objects.create(
            name='Alice',
            email='alice@example.com',
            password=make_password('pass123'),
            course='Web Dev'
        )
        project = Project.objects.create(
            student=student,
            title='E-Commerce Platform',
            description='Online store application',
            status='Submitted'
        )

        # Login as Admin
        self.client.post(reverse('admin_login'), {
            'email': 'admin1@creative.com',
            'password': 'admin123'
        })

        # Admin views projects
        proj_list_resp = self.client.get(reverse('admin_projects'))
        self.assertEqual(proj_list_resp.status_code, 200)
        self.assertContains(proj_list_resp, 'E-Commerce Platform')

        # Admin updates status to Approved
        update_status_resp = self.client.post(reverse('admin_project_status_update', kwargs={'project_id': project.id}), {
            'status': 'Approved'
        })
        self.assertRedirects(update_status_resp, reverse('admin_projects'))
        project.refresh_from_db()
        self.assertEqual(project.status, 'Approved')

        # Admin updates status to Rejected
        reject_resp = self.client.post(reverse('admin_project_status_update', kwargs={'project_id': project.id}), {
            'status': 'Rejected'
        })
        self.assertRedirects(reject_resp, reverse('admin_projects'))
        project.refresh_from_db()
        self.assertEqual(project.status, 'Rejected')

    def test_admin_change_password(self):
        # Login as Admin 1
        self.client.post(reverse('admin_login'), {
            'email': 'admin1@creative.com',
            'password': 'admin123'
        })

        # Change password
        resp = self.client.post(reverse('admin_change_password'), {
            'current_password': 'admin123',
            'new_password': 'newsecretpassword456',
            'confirm_password': 'newsecretpassword456'
        })
        self.assertRedirects(resp, reverse('admin_profile'))

        self.admin1.refresh_from_db()
        self.assertTrue(check_password('newsecretpassword456', self.admin1.password))
        self.assertFalse(check_password('admin123', self.admin1.password))

    def test_admin_profile_view(self):
        # Login as Admin 1
        self.client.post(reverse('admin_login'), {
            'email': 'admin1@creative.com',
            'password': 'admin123'
        })

        resp = self.client.get(reverse('admin_profile'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Administrator Profile')
        self.assertContains(resp, 'admin1')
        self.assertContains(resp, 'admin1@creative.com')

    def test_student_profile_view(self):
        student = Student.objects.create(
            name='Test Student Profile',
            email='testprofile@example.com',
            password=make_password('mypassword'),
            course='Data Science',
            phone='9876543210'
        )

        # Login as student
        self.client.post(reverse('student_login'), {
            'email': 'testprofile@example.com',
            'password': 'mypassword'
        })

        resp = self.client.get(reverse('student_profile'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Student Profile')
        self.assertContains(resp, 'Test Student Profile')
        self.assertContains(resp, 'Data Science')

    def test_student_change_password(self):
        student = Student.objects.create(
            name='Student Password Test',
            email='studentpwd@example.com',
            password=make_password('initialpassword123'),
            course='Python AI'
        )

        # Login as student
        self.client.post(reverse('student_login'), {
            'email': 'studentpwd@example.com',
            'password': 'initialpassword123'
        })

        # Change password
        resp = self.client.post(reverse('student_change_password'), {
            'current_password': 'initialpassword123',
            'new_password': 'brandnewpassword789',
            'confirm_password': 'brandnewpassword789'
        })
        self.assertRedirects(resp, reverse('student_profile'))

        student.refresh_from_db()
        self.assertTrue(check_password('brandnewpassword789', student.password))
        self.assertFalse(check_password('initialpassword123', student.password))

    def test_admin_project_detail_and_status_update(self):
        # Login as Admin 1
        self.client.post(reverse('admin_login'), {
            'email': 'admin1@creative.com',
            'password': 'admin123'
        })

        student = Student.objects.create(
            name='Project Tester',
            email='projtest@example.com',
            password=make_password('pass123'),
            course='Full Stack'
        )

        project = Project.objects.create(
            student=student,
            title='Inventory Pro',
            description='A full stack inventory system',
            project_link='https://github.com/proj/inventory',
            status='Submitted'
        )

        # Access project detail
        detail_resp = self.client.get(reverse('admin_project_detail', args=[project.id]))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, 'Inventory Pro')
        self.assertContains(detail_resp, 'Project Tester')
        self.assertContains(detail_resp, 'A full stack inventory system')

        # Approve project from detail page with next=detail
        status_resp = self.client.post(
            reverse('admin_project_status_update', args=[project.id]),
            {'status': 'Approved', 'next': 'detail'}
        )
        self.assertRedirects(status_resp, reverse('admin_project_detail', args=[project.id]))
        project.refresh_from_db()
        self.assertEqual(project.status, 'Approved')

    def test_exam_absent_student(self):
        self.client.post(reverse('admin_login'), {
            'email': 'admin1@creative.com',
            'password': 'admin123'
        })

        student = Student.objects.create(
            name='Absent Student',
            email='absent@example.com',
            password=make_password('pass123'),
            course='UI/UX Design'
        )

        exam = Exam.objects.create(
            title='Design Principles Exam',
            subject='UI/UX',
            exam_date='2026-06-01',
            total_marks=100
        )
        exam.students.add(student)

        # Mark absent
        absent_resp = self.client.post(reverse('admin_exam_marks_save', args=[exam.id]), {
            'student_id': student.id,
            'action': 'mark_absent'
        })
        self.assertRedirects(absent_resp, reverse('admin_exam_detail', args=[exam.id]))

        mark_rec = ExamMarks.objects.get(exam=exam, student=student)
        self.assertTrue(mark_rec.is_absent)
        self.assertEqual(mark_rec.grade, 'Absent')
        self.assertIsNone(mark_rec.marks_obtained)

        # Clear absent
        clear_resp = self.client.post(reverse('admin_exam_marks_save', args=[exam.id]), {
            'student_id': student.id,
            'action': 'clear_absent'
        })
        self.assertRedirects(clear_resp, reverse('admin_exam_detail', args=[exam.id]))
        mark_rec.refresh_from_db()
        self.assertFalse(mark_rec.is_absent)

    def test_student_multi_link_project(self):
        student = Student.objects.create(
            name='Link Tester',
            email='links@example.com',
            password=make_password('pass123'),
            course='Full Stack Development'
        )
        self.client.post(reverse('student_login'), {
            'email': 'links@example.com',
            'password': 'pass123'
        })

        # Submit project with multiple links
        resp = self.client.post(reverse('student_project_add'), {
            'title': 'E-Commerce Platform',
            'description': 'Full stack online shop',
            'link_urls': ['https://github.com/tester/ecommerce', 'https://ecommerce-live.demo.com', 'https://figma.com/file/12345/design'],
            'link_labels': ['GitHub Repo', 'Live Demo', 'Figma Prototype']
        })
        self.assertRedirects(resp, reverse('student_projects'))

        project = Project.objects.get(student=student, title='E-Commerce Platform')
        self.assertEqual(project.links.count(), 3)
        self.assertEqual(project.project_link, 'https://github.com/tester/ecommerce')
        
        all_links = project.all_links
        self.assertEqual(len(all_links), 3)
        self.assertEqual(all_links[0].label, 'GitHub Repo')
        self.assertEqual(all_links[1].label, 'Live Demo')
        self.assertEqual(all_links[2].label, 'Figma Prototype')

        # Edit project links
        edit_resp = self.client.post(reverse('student_project_edit', args=[project.id]), {
            'title': 'E-Commerce Platform v2',
            'description': 'Updated description',
            'link_urls': ['https://github.com/tester/ecommerce-v2'],
            'link_labels': ['GitHub Repo v2']
        })
        self.assertRedirects(edit_resp, reverse('student_projects'))

        project.refresh_from_db()
        self.assertEqual(project.title, 'E-Commerce Platform v2')
        self.assertEqual(project.links.count(), 1)
        self.assertEqual(project.links.first().url, 'https://github.com/tester/ecommerce-v2')
        self.assertEqual(project.project_link, 'https://github.com/tester/ecommerce-v2')

        # View project detail
        detail_resp = self.client.get(reverse('student_project_detail', args=[project.id]))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, 'E-Commerce Platform v2')
        self.assertContains(detail_resp, 'GitHub Repo v2')

    def test_student_project_multiple_files_upload_and_edit(self):
        student = Student.objects.create(
            name='Multi File Student',
            email='multifile@example.com',
            password=make_password('pass123'),
            course='Python & AI'
        )
        self.client.post(reverse('student_login'), {
            'email': 'multifile@example.com',
            'password': 'pass123'
        })

        file1 = SimpleUploadedFile("project_code.py", b"print('hello world')", content_type="text/plain")
        file2 = SimpleUploadedFile("architecture.pdf", b"%PDF-1.4 dummy content", content_type="application/pdf")

        # Submit project with multiple files
        resp = self.client.post(reverse('student_project_add'), {
            'title': 'AI Automation Suite',
            'description': 'Smart multi-agent system',
            'project_files': [file1, file2],
            'link_urls': ['https://github.com/tester/ai-suite'],
            'link_labels': ['GitHub Repo']
        })
        self.assertRedirects(resp, reverse('student_projects'))

        project = Project.objects.get(student=student, title='AI Automation Suite')
        self.assertEqual(project.files.count(), 2)
        self.assertEqual(len(project.all_files), 2)
        
        file_names = [f.filename for f in project.all_files]
        self.assertTrue(any('project_code' in fn for fn in file_names))
        self.assertTrue(any('architecture' in fn for fn in file_names))

        # Check detail page rendering
        detail_resp = self.client.get(reverse('student_project_detail', args=[project.id]))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, 'Attached Project Files & Documents (2)')
        self.assertContains(detail_resp, 'project_code')
        self.assertContains(detail_resp, 'architecture')

        # Edit project: delete first file and upload a new one
        first_file_id = project.files.first().id
        file3 = SimpleUploadedFile("dataset.zip", b"PKdummyzipcontent", content_type="application/zip")

        edit_resp = self.client.post(reverse('student_project_edit', args=[project.id]), {
            'title': 'AI Automation Suite v2',
            'description': 'Updated description',
            'delete_file_ids': [first_file_id],
            'project_files': [file3],
            'link_urls': ['https://github.com/tester/ai-suite'],
            'link_labels': ['GitHub Repo']
        })
        self.assertRedirects(edit_resp, reverse('student_projects'))

        project.refresh_from_db()
        self.assertEqual(project.files.count(), 2)
        remaining_names = [f.filename for f in project.files.all()]
        self.assertTrue(any('dataset' in fn for fn in remaining_names))
        self.assertTrue(any('architecture' in fn for fn in remaining_names))
        self.assertFalse(any(f.id == first_file_id for f in project.files.all()))



    def test_batch_attendance_workflow(self):
        # 1. Create students assigned to different batch time slots
        student1 = Student.objects.create(
            name="Alice Morning",
            email="alice@example.com",
            password=make_password("pass123"),
            course="Master In Full Stack Development",
            class_time="08:00 am to 10:00 am"
        )
        student2 = Student.objects.create(
            name="Bob Morning",
            email="bob@example.com",
            password=make_password("pass123"),
            course="Master In Flutter Development",
            class_time="08:00 am to 10:00 am"
        )
        student3 = Student.objects.create(
            name="Charlie Afternoon",
            email="charlie@example.com",
            password=make_password("pass123"),
            course="Master In Web Design",
            class_time="02:00 pm to 04:00 pm"
        )

        # 2. Login as Admin
        self.client.post(reverse('admin_login'), {
            'email': 'admin1@creative.com',
            'password': 'admin123'
        })

        # 3. Check Attendance Hub View
        hub_resp = self.client.get(reverse('admin_attendance_hub'))
        self.assertEqual(hub_resp.status_code, 200)
        self.assertContains(hub_resp, 'Batch Attendance Hub')
        self.assertContains(hub_resp, '08:00 am to 10:00 am')
        self.assertContains(hub_resp, '02:00 pm to 04:00 pm')

        # 4. Mark attendance for morning batch
        today_str = datetime.date.today().isoformat()
        batch_post_resp = self.client.post(
            f"{reverse('admin_attendance_batch')}?batch=08:00+am+to+10:00+am&date={today_str}",
            {
                'batch': '08:00 am to 10:00 am',
                'date': today_str,
                f'status_{student1.id}': 'Present',
                f'remarks_{student1.id}': 'On time',
                f'status_{student2.id}': 'Late',
                f'remarks_{student2.id}': 'Traffic delay 15m',
            }
        )
        self.assertEqual(batch_post_resp.status_code, 302)

        # Verify Attendance records in database
        att1 = Attendance.objects.get(student=student1, date=datetime.date.today())
        self.assertEqual(att1.status, 'Present')
        self.assertEqual(att1.remarks, 'On time')
        self.assertEqual(att1.time_slot, '08:00 am to 10:00 am')

        att2 = Attendance.objects.get(student=student2, date=datetime.date.today())
        self.assertEqual(att2.status, 'Late')
        self.assertEqual(att2.remarks, 'Traffic delay 15m')

        # 5. Verify Student.attendance_stats property
        stats1 = student1.attendance_stats
        self.assertEqual(stats1['total'], 1)
        self.assertEqual(stats1['present'], 1)
        self.assertEqual(stats1['percentage'], 100.0)

        # 6. Verify Attendance Monthly Report and CSV Export
        report_resp = self.client.get(reverse('admin_attendance_report'))
        self.assertEqual(report_resp.status_code, 200)
        self.assertContains(report_resp, 'Monthly Attendance Register')
        self.assertContains(report_resp, 'Alice Morning')

        csv_resp = self.client.get(f"{reverse('admin_attendance_report')}?export=csv")
        self.assertEqual(csv_resp.status_code, 200)
        self.assertEqual(csv_resp['Content-Type'], 'text/csv')
        self.assertIn('Alice Morning', csv_resp.content.decode())

        # 7. Student Portal Attendance View
        student_client = Client()
        student_client.post(reverse('student_login'), {
            'email': 'alice@example.com',
            'password': 'pass123'
        })
        std_att_resp = student_client.get(reverse('student_attendance'))
        self.assertEqual(std_att_resp.status_code, 200)
        self.assertContains(std_att_resp, 'My Attendance Portfolio')
        self.assertContains(std_att_resp, '08:00 am to 10:00 am')
        self.assertContains(std_att_resp, 'On time')