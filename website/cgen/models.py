from django.db import models, IntegrityError, transaction
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings

import os
import hashlib
import uuid

types = (
            ('tex', 'LaTeX Template'),
            ('svg', 'SVG Template'),
        )

# Create your models here.
def get_certificate_dir(instance, filename):
    return os.sep.join(('certificates', str(instance.participant.certificate.id), str(instance.id), filename))

def get_file_dir(instance, filename):
    os.makedirs(settings.CERTIFICATES_PATH, exist_ok=True)
    ext = filename.split('.')[-1]
    return os.path.join('certificates', 'templates', f'{uuid.uuid4()}.{ext}')


def get_certificate_dir(instance, filename):
    path = os.path.join(settings.CERTIFICATES_PATH,
        str(instance.participant.certificate.id), str(instance.id)
    )
    os.makedirs(path, exist_ok=True)

    return os.path.join('certificates',
        str(instance.participant.certificate.id), str(instance.id),
        filename
    )


class Event(models.Model):
    """
        Event for which the participants claim certificate.
    """
    
    # Name of the Event
    name = models.CharField(max_length=1000)

    # Description for the event
    description = models.TextField()

    # Start date and time of the Event
    start_date = models.DateTimeField('Start date and time of the Event',
        default=timezone.now, null=True)

    # End date and time of the Event
    end_date = models.DateTimeField('End date and time of the Event',
        default=timezone.now, null=True)
    # Default set to infinite value


    # Publish the event for the participants
    is_published = models.BooleanField(default=False)

    # One who creates the event (organiser)
    creator = models.ForeignKey(User, null=True, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    
    updated_at = models.DateTimeField(auto_now=True)
    
    published_on = models.DateTimeField(null=True, blank=True)


    def __str__(self):
        return self.name


    def publish(self):
        self.is_published = True
        self.published_on = timezone.now()
        self.save(update_fields=['is_published', 'published_on'])

    def unpublish(self):
        self.is_published = False
        self.save(update_fields=['is_published'])


class Certificate(models.Model):
    """
       Certificate for the participants
    """

    # Event to which the certificate belongs
    event = models.ForeignKey(Event, on_delete=models.CASCADE)

    # Type of certificate
    description = models.TextField()

    template_type = models.CharField(max_length=24, choices=types)

    # Template for the certificate 
    template = models.FileField(
            upload_to=get_file_dir,
            null=True, blank=True, default=None,
            help_text='Upload LaTeX template for the certificate'
        )
    background = models.FileField(
            upload_to=get_file_dir,
            null=True, blank=True, default=None,
            help_text='Upload background for the certificate in png or jpg',
        )
    variables = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return 'Certificate for {0}'.format(self.event.name)


class Participant(models.Model):

    email = models.EmailField(max_length=1000)

    certificate = models.ForeignKey('Certificate', on_delete=models.CASCADE)

    details = models.JSONField(default=dict)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # The same email may appear more than once on a certificate (for
        # example one person with several course grades); that person then
        # downloads all their certificates together.
        indexes = [models.Index(fields=['certificate', 'email'])]

    def __str__(self):
        return self.email



class CertificateManager(models.Model):

    certificate_file = models.FileField(
            upload_to=get_certificate_dir,
            null=True, blank=True, default=None,
        )

    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)

    is_created = models.BooleanField(default=False)

    has_downloaded = models.BooleanField(default=False)

    certificate_creation_time = models.DateTimeField(null=True, blank=True)

    download_time  = models.DateTimeField(null=True, blank=True)

    serial_key_long = models.CharField(unique=True, max_length=300,
                                       null=True, default=None)

    serial_key_short = models.CharField(unique=True, max_length=16,
                                        null=True, default=None)

    created_at = models.DateTimeField(auto_now_add=True)
    
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.participant.certificate.event} - {self.participant.email}"
    
    def assign_serial_key(self):
        """Give this certificate its serial key, once.

        The key is printed on the certificate and in its QR code, so it must
        never change after it has been issued. The first certificate for an
        email gets the same key as before (sha1 of email + certificate id);
        further certificates for the same email get the next free key.
        """
        if self.serial_key_short:
            return
        email = self.participant.email
        certificate_id = self.participant.certificate_id
        for attempt in range(5):
            a = 0
            while True:
                source = f'{email}{certificate_id}' + (str(a) if a else '')
                long_key = hashlib.sha1(source.encode('utf-8')).hexdigest()
                if not CertificateManager.objects.filter(
                        serial_key_long=long_key).exists():
                    break
                a += 1
            for chars in range(4, 17):  # serial_key_short holds 16 chars
                short_key = long_key[:chars]
                if not CertificateManager.objects.filter(
                        serial_key_short=short_key).exists():
                    break
            self.serial_key_long = long_key
            self.serial_key_short = short_key
            try:
                with transaction.atomic():
                    self.save(update_fields=['serial_key_long',
                                             'serial_key_short'])
                return
            except IntegrityError:
                # Another request took this key at the same moment; retry.
                self.serial_key_long = self.serial_key_short = None
        raise IntegrityError('Could not assign a unique serial key')

    def get_serial_key_short(self):
        return self.serial_key_short


##############################################################################
