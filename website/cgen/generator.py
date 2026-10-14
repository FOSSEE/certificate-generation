import glob
import logging
import os
import subprocess
import uuid
from string import Template
import segno
import ast
import re
from xml.sax.saxutils import escape as xml_escape

from pathlib import Path
from django.core.files import File
from django.conf import settings
from django.contrib.sites.models import Site
from django.utils.text import slugify
from django.urls import reverse
from cgen.models import CertificateManager, Participant, Certificate

logger = logging.getLogger(__name__)


LATEX_SPECIAL = {
    '\\': r'\textbackslash{}',
    '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#', '_': r'\_',
    '{': r'\{', '}': r'\}',
    '~': r'\textasciitilde{}', '^': r'\textasciicircum{}',
    '<': r'\textless{}', '>': r'\textgreater{}',
}
LATEX_SPECIAL_RE = re.compile('|'.join(re.escape(c) for c in LATEX_SPECIAL))


def escape_value(value, template_type):
    """Make a participant's value safe to paste into the template.

    Without this, "Science & Technology" makes an SVG invalid and fails
    generation, and in LaTeX & % # _ break the build (or run commands).
    """
    value = str(value)
    if template_type == 'svg':
        return xml_escape(value, {'"': '&quot;', "'": '&apos;'})
    if template_type == 'tex':
        return LATEX_SPECIAL_RE.sub(lambda m: LATEX_SPECIAL[m.group()], value)
    return value


def _get_domain():
    return Site.objects.get_current().domain


def find_participants(certificate_id, email):
    """All participants of a certificate with this email, oldest first.

    Emails are matched ignoring case: "Xyz@Example.com" in the CSV must
    match "xyz@example.com" typed on the download page. One email can have
    several rows (for example several courses).
    """
    return list(Participant.objects.filter(
        certificate=certificate_id, email__iexact=(email or '').strip()
    ).order_by('id'))


def get_certificate(certificate_id, email):
    """Generate the certificate of the first participant with this email.
    Kept for callers that only need one; see find_participants()."""
    participants = find_participants(certificate_id, email)
    if not participants:
        return (None, False)
    return generate(participants[0])


def _certificate_manager(participant):
    # filter().first() rather than get_or_create(): two simultaneous first
    # downloads could otherwise create two records and break later ones.
    cm = CertificateManager.objects.filter(
        participant=participant).order_by('id').first()
    if cm is None:
        cm = CertificateManager.objects.create(participant=participant)
    cm.assign_serial_key()
    return cm


def get_details(participant):
    certificate = participant.certificate
    email = participant.email
    certificate_details = {}
    cm = _certificate_manager(participant)
    certificate_details['template'] = certificate.template.path
    certificate_details['template_type'] = certificate.template_type
    info = {key: escape_value(value, certificate.template_type)
            for key, value in participant.details.items()}
    key = cm.serial_key_short
    info['serial_key'] = key
    domain = _get_domain()
    scheme = getattr(settings, 'SITE_SCHEME', 'https')
    info['qr_code'] = f"{scheme}://{domain}{reverse('verify_key', args=[key])}"
    certificate_details['info'] = info
    path = os.path.join(settings.CERTIFICATES_PATH, str(certificate.id))
    os.makedirs(path, exist_ok=True)
    certificate_details['path'] = path
    certificate_details['file_name'] = (
        f"{slugify(email)}-{certificate.id}-{participant.id}")
    return cm, certificate_details


def generate(participant):
    cm, certificate_details = get_details(participant)
    certificate, email = participant.certificate_id, participant.email
    template = certificate_details['template']
    info = certificate_details['info']
    cpath = certificate_details['path']
    template_type = certificate_details['template_type']

    # Every request gets its own file names, so participants downloading at
    # the same moment never read or delete each other's files (before this,
    # all SVG certificates shared one "qrcode.png" and could get the wrong
    # QR code). Files stay in the certificate folder so templates that use
    # other files placed there keep working.
    job = f"{certificate_details['file_name']}-{uuid.uuid4().hex[:8]}"
    try:
        # surrogateescape: a template saved in another encoding is passed
        # through byte for byte instead of failing.
        with open(template, 'r', encoding='utf-8',
                  errors='surrogateescape') as template_file:
            content = Template(template_file.read()).safe_substitute(info)

        if template_type == 'svg':
            qr_name = f'{job}-qrcode.png'
            segno.make(info['qr_code']).save(
                os.path.join(cpath, qr_name), scale=10, light=None)
            content = content.replace('qrcode.png', qr_name)
            command = 'participant_cert_svg'
        else:
            command = 'participant_cert'

        with open(os.path.join(cpath, f'{job}.{template_type}'), 'w',
                  encoding='utf-8', errors='surrogateescape') as source:
            source.write(content)

        return_value, msg = _make_certificate_certificate(cpath, job, command)
        if return_value != 0:
            logger.error('Certificate %s for %s failed (exit %s): %s',
                         certificate, email, return_value,
                         msg.decode(errors='replace')[-2000:])
            return [cm, False]

        _store_pdf(cm, Path(cpath, f'{job}.pdf'),
                   f"{certificate_details['file_name']}.pdf")
    except Exception:
        logger.exception('Certificate %s for %s failed', certificate, email)
        return [cm, False]
    finally:
        for leftover in glob.glob(os.path.join(glob.escape(cpath), f'{job}*')):
            try:
                os.remove(leftover)
            except OSError:
                pass
    return [cm, True]


def _store_pdf(cm, pdf_path, name):
    """Save the new PDF and remove the one from the previous download, so a
    new copy is not left behind on disk every time someone downloads."""
    old_name = cm.certificate_file.name if cm.certificate_file else None
    with pdf_path.open(mode='rb') as f:
        cm.certificate_file = File(f, name=name)
        cm.save()
    if old_name and old_name != cm.certificate_file.name:
        cm.certificate_file.storage.delete(old_name)


def _make_certificate_certificate(path, file_name, command='participant_cert'):
    # Use the project's Makefile directly instead of a copy per certificate
    # folder, so changes to it apply everywhere.
    makefile = os.path.join(settings.BASE_DIR, 'Makefile')
    result = subprocess.run(
        ['timeout', str(settings.TIME_OUT), 'make', '-f', makefile, '-C', path,
         command, f'file_name={file_name}'],
        capture_output=True, stdin=subprocess.DEVNULL,
    )
    return result.returncode, result.stderr + result.stdout[-2000:]
