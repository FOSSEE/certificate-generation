import os
import subprocess
from string import Template
import shutil
import segno
import ast

from pathlib import Path
from django.core.files import File
from django.conf import settings
from django.contrib.sites.models import Site
from django.utils.text import slugify
from django.urls import reverse
from cgen.models import CertificateManager, Participant, Certificate


def _get_domain():
    return Site.objects.get_current().domain


def get_certificate(certificate_id, email):
    try:
        participant = Participant.objects.get(email=email, certificate=certificate_id)
    except Participant.DoesNotExist:
        return (None, False)
    return  generate(certificate_id, email)


def get_details(certificate_id, email):
    certificate = Certificate.objects.get(id=certificate_id)
    participant = Participant.objects.get(email=email, certificate=certificate)
    certificate_details = {}
    cm, created = CertificateManager.objects.get_or_create(
                    participant=participant)
    key = cm.generate_key()
    cm.set_serial_key_short(key)
    certificate_details['template'] = certificate.template.path
    certificate_details['template_type'] = certificate.template_type
    info = participant.details.copy()
    key = cm.get_serial_key_short()
    info['serial_key'] = key
    domain = _get_domain()
    scheme = getattr(settings, 'SITE_SCHEME', 'https')
    info['qr_code'] = f"{scheme}://{domain}{reverse('verify_key', args=[key])}"
    certificate_details['info'] = info
    path = os.path.join(settings.CERTIFICATES_PATH, str(certificate.id))
    os.makedirs(path, exist_ok=True)
    certificate_details['path'] = path
    makefile_path = os.path.join(path, "Makefile")
    if not os.path.exists(makefile_path):
        shutil.copy2(os.path.join(settings.BASE_DIR, "Makefile"), makefile_path)
    certificate_details['file_name'] = f"{slugify(email)}-{certificate.id}"
    return cm, certificate_details


def generate(certificate, email):
    cm, certificate_details = get_details(certificate, email)
    template = certificate_details['template']
    info = certificate_details['info']
    cpath = certificate_details['path']
    file_name = certificate_details['file_name']
    template_type = certificate_details['template_type']
    msg = None
    has_error = False
    try:
        template_file = open(template, 'r')
        content = Template(template_file.read())
        template_file.close()
        if template_type == 'tex':
            content_tex = content.safe_substitute(info)
            create_tex = open('{0}/{1}.tex'.format(cpath, file_name), 'w')
            create_tex.write(content_tex)
            create_tex.close()
            return_value, msg = _make_certificate_certificate(cpath, file_name,
                                    command='participant_cert')
            if return_value == 0:
                path = Path('{0}/{1}.pdf'.format(cpath, file_name))
                with path.open(mode='rb') as f:
                    cm.certificate_file = File(f, name=path.name)
                    cm.save()
            else:
                has_error = True
        if template_type == 'svg':
            content_svg = content.safe_substitute(info)
            create_svg = open('{0}/{1}.svg'.format(cpath, file_name), 'w')
            create_svg.write(content_svg)
            create_svg.close()

            # create QR code
            qrcode_text = info['qr_code']
            img = segno.make(qrcode_text)
            qrpath = os.path.join(cpath, 'qrcode.png')
            img.save(qrpath, scale=10, light=None)

            return_value, msg = _make_certificate_certificate(cpath, file_name,
                                    command='participant_cert_svg')
            if return_value == 0:
                path = Path('{0}/{1}.pdf'.format(cpath, file_name))
                with path.open(mode='rb') as f:
                    cm.certificate_file = File(f, name=path.name)
                    cm.save()
            else:
                has_error = True
            _clean_certificate_certificate(cpath, file_name)
    except Exception as e:
        has_error = True
        msg = e
    return [cm, not has_error] 
            

def _make_certificate_certificate(path, file_name, command='participant_cert'):
    result = subprocess.run(
        ['timeout', str(settings.TIME_OUT), 'make', '-C', path, command,
        f'file_name={file_name}'],  capture_output=True
    )
    return result.returncode, result.stderr


def _clean_certificate_certificate(path, file_name):
    subprocess.run(
        ['make', '-C', path, 'clean', f'file_name={file_name}'],
        check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
