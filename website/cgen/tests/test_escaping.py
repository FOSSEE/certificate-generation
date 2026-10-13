import shutil
import subprocess
from unittest import skipUnless

from django.test import SimpleTestCase

from cgen import generator
from cgen.generator import escape_value
from cgen.models import Participant
from cgen.tests import templates
from cgen.tests.helpers import CgenTestCase

NASTY = 'Science & Tech <R&D> "Lab" 50% #1 a_b {x} ~^ \\ $5'


def pdf_text(path):
    return subprocess.run(['pdftotext', path, '-'], capture_output=True,
                          text=True).stdout


class EscapeValueTests(SimpleTestCase):

    def test_svg(self):
        self.assertEqual(escape_value('A & B <C> "D"', 'svg'),
                         'A &amp; B &lt;C&gt; &quot;D&quot;')

    def test_tex(self):
        self.assertEqual(escape_value(r'50% & #1 a_b {x} $5 ~ ^ \ <>', 'tex'),
                         r'50\% \& \#1 a\_b \{x\} \$5 \textasciitilde{} '
                         r'\textasciicircum{} \textbackslash{} '
                         r'\textless{}\textgreater{}')

    def test_plain_text_unchanged(self):
        for kind in ('svg', 'tex'):
            self.assertEqual(escape_value('Abc Xyz', kind), 'Abc Xyz')


@skipUnless(shutil.which('pdftotext'), 'pdftotext not installed')
class GenerateWithSpecialCharactersTests(CgenTestCase):

    def generate(self, template, kind):
        certificate = self.make_certificate(template, kind)
        Participant.objects.create(
            certificate=certificate, email='a@x.com',
            details={'name': 'Abc', 'institute': NASTY})
        cm, ok = generator.get_certificate(certificate.id, 'a@x.com')
        self.assertTrue(ok, 'certificate generation failed')
        return pdf_text(cm.certificate_file.path)

    @skipUnless(shutil.which('rsvg-convert'), 'rsvg-convert not installed')
    def test_svg_certificate(self):
        text = self.generate(templates.SVG, 'svg')
        self.assertIn('Science & Tech <R&D> "Lab" 50%', text)

    @skipUnless(shutil.which('pdflatex'), 'pdflatex not installed')
    def test_tex_certificate(self):
        text = self.generate(templates.TEX, 'tex')
        self.assertIn('Science & Tech <R&D>', text)
        self.assertIn('50% #1', text)
        self.assertIn('{x}', text)
