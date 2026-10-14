from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.urls import reverse

from cgen.csv_import import CSVImportError, parse_participants
from cgen.models import Participant
from cgen.tests.helpers import CgenTestCase


class ParseParticipantsTests(SimpleTestCase):

    def parse(self, data):
        if isinstance(data, str):
            data = data.encode()
        return parse_participants(data)

    def test_plain_csv(self):
        rows, problems = self.parse('email,name,institute\na@x.com,Ram,IITB\n')
        self.assertEqual(rows, [('a@x.com', {'name': 'Ram', 'institute': 'IITB'})])
        self.assertEqual(problems, [])

    def test_excel_csv_utf8_with_bom_and_crlf(self):
        rows, _ = self.parse(b'\xef\xbb\xbfemail,name\r\na@x.com,Ram\r\n')
        self.assertEqual(rows, [('a@x.com', {'name': 'Ram'})])

    def test_quoted_cell_containing_comma(self):
        rows, _ = self.parse(
            'email,name,institute\r\n'
            'a@x.com,Ram,"Dept of CS, IIT Bombay"\r\n')
        self.assertEqual(rows[0][1]['institute'], 'Dept of CS, IIT Bombay')

    def test_quoted_cells_on_every_row(self):
        body = ''.join(f'p{i}@x.com,P{i},"A, B"\r\n' for i in range(40))
        rows, _ = self.parse('email,name,institute\r\n' + body)
        self.assertEqual(len(rows), 40)

    def test_unicode_names_beyond_first_kilobyte(self):
        name = 'राम' * 400  # Devanagari, multi-byte in UTF-8
        rows, _ = self.parse(f'email,name\nab@x.com,{name}\n')
        self.assertEqual(rows[0][1]['name'], name)

    def test_legacy_windows_encoding(self):
        rows, _ = self.parse('email,name\r\na@x.com,Ren\xe9\r\n'.encode('cp1252'))
        self.assertEqual(rows[0][1]['name'], 'Ren\xe9')

    def test_semicolon_separator(self):
        rows, _ = self.parse('email;name\r\na@x.com;Ram\r\n')
        self.assertEqual(rows, [('a@x.com', {'name': 'Ram'})])

    def test_tab_separator(self):
        rows, _ = self.parse('email\tname\na@x.com\tRam\n')
        self.assertEqual(rows, [('a@x.com', {'name': 'Ram'})])

    def test_blank_columns_and_rows_ignored(self):
        rows, problems = self.parse(
            'email,name,,\r\na@x.com,Ram,,\r\n,,,\r\n\r\n')
        self.assertEqual(rows, [('a@x.com', {'name': 'Ram'})])
        self.assertEqual(problems, [])

    def test_headings_normalised(self):
        rows, _ = self.parse(' Email , NAME ,Course Name\na@x.com,Ram,Python\n')
        self.assertEqual(rows[0][1], {'name': 'Ram', 'course_name': 'Python'})

    def test_email_lowercased_and_trimmed(self):
        rows, _ = self.parse('email,name\n  Ram@Example.COM ,Ram\n')
        self.assertEqual(rows[0][0], 'ram@example.com')

    def test_short_rows_padded(self):
        rows, _ = self.parse('email,name,institute\na@x.com,Ram\n')
        self.assertEqual(rows[0][1], {'name': 'Ram', 'institute': ''})

    def test_missing_and_invalid_email_reported(self):
        rows, problems = self.parse(
            'email,name\n,NoEmail\nnot-an-email,Bad\nok@x.com,Ok\n')
        self.assertEqual([r[0] for r in rows], ['ok@x.com'])
        self.assertEqual(len(problems), 2)
        self.assertIn('Row 2', problems[0])
        self.assertIn('Row 3', problems[1])

    def test_missing_required_heading_lists_found_columns(self):
        with self.assertRaisesRegex(CSVImportError, 'Missing: name.*Found: email, full_name'):
            self.parse('email,Full Name\na@x.com,Ram\n')

    def test_duplicate_heading_rejected(self):
        with self.assertRaisesRegex(CSVImportError, 'more than once: name'):
            self.parse('email,name,name\na@x.com,A,B\n')

    def test_reserved_heading_rejected(self):
        with self.assertRaisesRegex(CSVImportError, 'serial_key'):
            self.parse('email,name,serial_key\na@x.com,A,1\n')

    def test_xlsx_rejected_with_explanation(self):
        with self.assertRaisesRegex(CSVImportError, 'Excel'):
            self.parse(b'PK\x03\x04rest-of-zip')

    def test_empty_file(self):
        with self.assertRaisesRegex(CSVImportError, 'empty'):
            self.parse(b'')


class UploadViewTests(CgenTestCase):

    def setUp(self):
        super().setUp()
        self.certificate = self.make_certificate('<svg/>')
        self.url = reverse('upload_csv_participants', args=[self.certificate.id])

    def upload(self, content):
        return self.client.post(self.url, {
            'csv_file': SimpleUploadedFile('list.csv', content, 'text/csv')},
            follow=True)

    def test_excel_file_uploads(self):
        response = self.upload(
            b'\xef\xbb\xbfEmail,Name,Institute\r\n'
            b'a@x.com,Ram,"IIT Bombay, Mumbai"\r\nb@x.com,Rahul,KCCMS\r\n')
        self.assertContains(response, '2 added, 0 already on the list')
        p = Participant.objects.get(email='a@x.com')
        self.assertEqual(p.details, {'name': 'Ram', 'institute': 'IIT Bombay, Mumbai'})

    def test_same_email_on_several_rows_is_kept(self):
        response = self.upload(b'email,name,course\n'
                               b'a@x.com,Ram,Python\na@x.com,Ram,Scilab\n')
        self.assertContains(response, '2 added')
        self.assertEqual(Participant.objects.filter(email='a@x.com').count(), 2)

    def test_reupload_skips_exact_repeats_ignoring_email_case(self):
        Participant.objects.create(certificate=self.certificate,
                                   email='A@x.com', details={'name': 'Ram'})
        response = self.upload(b'email,name\na@X.com,Ram\na@x.com,Ram\n'
                               b'b@x.com,New\n')
        self.assertContains(response, '1 added, 2 already on the list')
        self.assertEqual(Participant.objects.count(), 2)

    def test_changed_details_are_added_not_overwritten(self):
        Participant.objects.create(certificate=self.certificate,
                                   email='a@x.com', details={'name': 'Old'})
        self.upload(b'email,name\na@x.com,New\n')
        self.assertEqual(
            sorted(p.details['name'] for p in Participant.objects.all()),
            ['New', 'Old'])

    def test_error_message_shown(self):
        response = self.upload(b'mail,name\na@x.com,Ram\n')
        self.assertContains(response, 'Missing: email')
        self.assertEqual(Participant.objects.count(), 0)

    def test_other_organiser_forbidden(self):
        from django.contrib.auth.models import User
        other = User.objects.create_user('other', password='pw')
        self.client.force_login(other)
        response = self.upload(b'email,name\na@x.com,Ram\n')
        self.assertEqual(response.status_code, 403)
