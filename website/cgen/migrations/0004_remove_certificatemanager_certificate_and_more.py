# Generated by Django 4.1.7 on 2023-04-10 07:53

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cgen', '0003_certificatemanager_certificate_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='certificatemanager',
            name='certificate',
        ),
        migrations.RemoveField(
            model_name='participant',
            name='user',
        ),
    ]
