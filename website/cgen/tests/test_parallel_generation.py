import glob
import os
import shutil
import subprocess
import tempfile
from unittest import mock, skipUnless

import segno
from PIL import Image

from cgen import generator
from cgen.models import Participant
from cgen.tests import templates
from cgen.tests.helpers import CgenTestCase


# Where templates.SVG draws the QR image, in viewBox units (= mm).
QR_BOX = (20, 150, 40)  # x, y, width/height
PAGE_WIDTH = 297


def qr_modules_in_pdf(pdf_path, size):
    """Read back the QR code printed on the PDF as a grid of dark (True) and
    light (False) modules.

    The page is rendered to an image and the QR area is sampled, so the
    check does not depend on how a given rsvg-convert version stores the
    picture inside the PDF.
    """
    out = tempfile.mkdtemp()
    try:
        subprocess.run(['pdftoppm', '-r', '300', '-gray', '-png', '-singlefile',
                        pdf_path, f'{out}/page'], check=True)
        page = Image.open(f'{out}/page.png').convert('L')
    finally:
        shutil.rmtree(out)
    scale = page.width / PAGE_WIDTH
    x0, y0, width = (v * scale for v in QR_BOX)
    step = width / size
    return [[page.getpixel((int(x0 + (x + .5) * step),
                            int(y0 + (y + .5) * step))) < 128
             for x in range(size)] for y in range(size)]


def qr_matches(pdf_path, url):
    """True if the PDF's QR code encodes ``url``."""
    border = 4  # segno's default quiet zone, in modules
    matrix = segno.make(url).matrix
    size = len(matrix) + 2 * border
    found = qr_modules_in_pdf(pdf_path, size)
    inner = [row[border:border + len(matrix)]
             for row in found[border:border + len(matrix)]]
    return inner == [[bool(m) for m in row] for row in matrix]


tools = all(shutil.which(t) for t in ('rsvg-convert', 'pdftoppm'))


@skipUnless(tools, 'rsvg-convert and pdftoppm needed')
class GenerationFilesTests(CgenTestCase):

    def setUp(self):
        super().setUp()
        self.certificate = self.make_certificate(templates.SVG, 'svg')
        Participant.objects.create(certificate=self.certificate, email='a@x.com',
                                   details={'name': 'A', 'institute': 'I'})
        self.folder = os.path.join(self.media, 'certificates',
                                   str(self.certificate.id))

    def test_other_requests_files_are_not_touched(self):
        os.makedirs(self.folder, exist_ok=True)
        in_flight = ['qrcode.png', 'b-x-com-1-0000aaaa.svg',
                     'b-x-com-1-0000aaaa-qrcode.png', 'notes.aux']
        for name in in_flight:
            open(os.path.join(self.folder, name), 'w').close()

        cm, ok = generator.get_certificate(self.certificate.id, 'a@x.com')

        self.assertTrue(ok)
        files = [f for f in os.listdir(self.folder)
                 if os.path.isfile(os.path.join(self.folder, f))]
        self.assertEqual(sorted(files), sorted(in_flight),
                         'only this request\'s own files should be removed')

    def test_qr_code_matches_participant(self):
        cm, ok = generator.get_certificate(self.certificate.id, 'a@x.com')
        self.assertTrue(ok)
        url = f'https://example.com/certificate/verify/{cm.serial_key_short}/'
        self.assertTrue(qr_matches(cm.certificate_file.path, url))
        self.assertFalse(qr_matches(cm.certificate_file.path, url + 'x'))

    def test_repeat_download_replaces_previous_pdf(self):
        cm, _ = generator.get_certificate(self.certificate.id, 'a@x.com')
        first = cm.certificate_file.path
        cm, _ = generator.get_certificate(self.certificate.id, 'a@x.com')
        pdfs = glob.glob(os.path.join(os.path.dirname(first), '*.pdf'))
        self.assertEqual(pdfs, [cm.certificate_file.path])


@skipUnless(tools, 'rsvg-convert and pdftoppm needed')
class OverlappingDownloadsTests(CgenTestCase):
    """Two participants downloading at the same moment each get their own QR
    code. All SVG certificates used to share one qrcode.png, and the second
    download's "make clean" deleted the first one's files.

    The overlap is made deterministic: while the first participant's PDF is
    being made, the second participant's whole download runs.
    """

    def setUp(self):
        super().setUp()
        self.certificate = self.make_certificate(templates.SVG, 'svg')
        for email in ('first@x.com', 'second@x.com'):
            Participant.objects.create(certificate=self.certificate, email=email,
                                       details={'name': email, 'institute': 'I'})

    def test_overlapping_downloads(self):
        real_make = generator._make_certificate_certificate
        results = {}

        def make_with_overlap(path, file_name, command):
            if 'second' not in results and file_name.startswith('first'):
                results['second'] = generator.get_certificate(
                    self.certificate.id, 'second@x.com')
            return real_make(path, file_name, command)

        with mock.patch.object(generator, '_make_certificate_certificate',
                               make_with_overlap):
            results['first'] = generator.get_certificate(
                self.certificate.id, 'first@x.com')

        for who in ('first', 'second'):
            cm, ok = results[who]
            self.assertTrue(ok, f'{who} download failed')
            url = f'https://example.com/certificate/verify/{cm.serial_key_short}/'
            self.assertTrue(qr_matches(cm.certificate_file.path, url),
                            f'{who} got the wrong QR code')
