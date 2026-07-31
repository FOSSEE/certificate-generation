from django.db import models, IntegrityError
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
        constraints = [
            models.UniqueConstraint(
                fields=['email', 'certificate'],
                name='unique_participant_per_certificate'
            )
        ]

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
    
    def generate_key(self, a = 0):
        email = self.participant.email
        certificate_id = self.participant.certificate.id
        if a != 0:
            s = f'{email}{certificate_id}{a}'
        else:
            s = f'{email}{certificate_id}'
        to_hash = bytes(s, 'utf-8')
        hashk = hashlib.sha1(to_hash).hexdigest()
        self.set_serial_key_long(hashk, a)
        return hashk

    def set_serial_key_long(self, key, a):
        try:
            self.serial_key_long = key
            self.save()
        except IntegrityError:
            a += 1
            self.generate_key(a)

    def set_serial_key_short(self, lkey, chars=4):
        try:
            self.serial_key_short = lkey[0:chars]
            self.save()
        except IntegrityError:
            chars += 1
            self.set_serial_key_short(lkey, chars)

    def get_serial_key_short(self):
        return self.serial_key_short


##############################################################################
