from django.shortcuts import render, get_object_or_404
from django.template import RequestContext
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.utils.text import slugify
from django.contrib.auth import login, logout
from cgen import generator, verification
from cgen.csv_import import CSVImportError, parse_participants

from cgen.models import Certificate, Participant, Event, CertificateManager
from cgen.forms import EventForm, CertificateForm, OrganizerRegistrationForm
import zipfile
from io import BytesIO
import json


def check_event_owner(request, event):
    if request.user.is_superuser:
        return
    if event.creator_id != request.user.id:
        raise PermissionDenied


def organizer_register(request):
    if request.user.is_authenticated:
        return redirect('organizer_dashboard')

    if request.method == 'POST':
        form = OrganizerRegistrationForm(request.POST)

        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False   # admin must approve
            user.is_staff = False
            user.save()
            messages.success(
                request,
                'Registration successful. Your account is pending admin approval.'
            )
            return redirect('login')
    else:
        form = OrganizerRegistrationForm()

    return render(request, 'registration/register.html', {
        'form': form
    })


@login_required
def organiser_logout(request):
    if request.method == 'POST':
        logout(request)
        messages.success(request, 'You have been logged out.')
        return redirect('login')

    return render(request, 'registration/logout.html')


def events(request):
    events = Event.objects.filter(is_published=True)
    context = {'events': events}
    return render(request, 'index.html', context)


@login_required
def certificate_download_all(request, certificate_id):
    certificate = get_object_or_404(Certificate, id=certificate_id)
    check_event_owner(request, certificate.event)
    context = {'certificate': certificate}
    participants = certificate.participant_set.all()
    details = {}
    for participant in participants:
        info = eval(f'{participant.details}')
        details[participant.email] = info['name']
    context['details'] = details
    return render(request, 'download_all.html', context)


def certificate_download(request, certificate_id, email=None):
    context= {}
    certificate = get_object_or_404(Certificate, id=certificate_id)
    context['certificate'] = certificate
    ci = RequestContext(request)
    if request.method == 'POST':
        email = request.POST.get('email').strip()
    elif email is not None:
        email = email
    else:
        return render(request, 'download.html', context)
    cm, s = generator.get_certificate(certificate_id, email)
    if not s:
        context["notregistered"] = 1
        return render(request, 'download.html', context)
    if s:
        filename = f"{slugify(email)}-certificate-{certificate_id}.pdf"
        response = HttpResponse(cm.certificate_file, content_type="application/pdf")
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


def verify(request, key=None):
    context = {}
    if key is None and request.method == 'GET':
        return render(request, 'verification.html', context)
    if key is not None:
        skey = key
    elif request.method == 'POST':
        skey = request.POST.get('key').strip()

    details, description = verification.verify(skey)
    if not details['Authentic']:
        context['invalidserial'] = 1
        return render(request, 'verification.html', context)

    context['details'] = details
    context['has_details'] = details['Authentic']
    context['description'] = description
    return render(request, 'verification_details.html', context)


@login_required
def upload_csv_participants(request, certificate_id):
    certificate = get_object_or_404(Certificate, pk=certificate_id)
    check_event_owner(request, certificate.event)
    context = {'certificate': certificate}

    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        if csv_file is None:
            messages.warning(request, "Please choose a CSV file to upload.")
            return render(request, 'organizer/upload_participants.html', context)
        try:
            rows, problems = parse_participants(csv_file.read())
        except CSVImportError as e:
            messages.warning(request, str(e))
            return render(request, 'organizer/upload_participants.html', context)

        added, updated, unchanged = _save_participants(rows, certificate, problems)
        for problem in problems:
            messages.info(request, problem)
        if added or updated or unchanged:
            messages.success(
                request,
                f"Upload complete: {added} added, {updated} updated, "
                f"{unchanged} unchanged"
                + (f", {len(problems)} row(s) need attention (see below)."
                   if problems else "."))
        else:
            messages.warning(request, "No participants were found in the file.")
    return render(request, 'organizer/upload_participants.html', context)


def _save_participants(rows, certificate, problems):
    """Add or update participants. An email that is already on the list
    gets its details replaced by the row from the file."""
    added = updated = unchanged = 0
    seen = {}
    for email, details in rows:
        if email in seen:
            problems.append(
                f"{email} appears more than once in the file; "
                f"only the last row was kept.")
        seen[email] = details
    for email, details in seen.items():
        participant = Participant.objects.filter(
            certificate=certificate, email__iexact=email).first()
        if participant is None:
            Participant.objects.create(
                certificate=certificate, email=email, details=details)
            added += 1
        elif participant.details != details:
            participant.details = details
            participant.save()
            updated += 1
        else:
            unchanged += 1
    return added, updated, unchanged


@login_required
def organizer_dashboard(request):
    events = Event.objects.filter(creator=request.user).order_by('-start_date')
    return render(request, 'organizer/dashboard.html', {'events': events})


@login_required
def create_event(request):
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.creator = request.user
            event.is_published = False
            event.save()
            return redirect('event_detail', event_id=event.id)
    else:
        form = EventForm()

    return render(request, 'organizer/event_form.html', {'form': form})


@login_required
def edit_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    check_event_owner(request, event)

    if request.method == 'POST':
        form = EventForm(request.POST, instance=event)

        if form.is_valid():
            form.save()
            messages.success(request, 'Event updated successfully.')
            return redirect('event_detail', event_id=event.id)
    else:
        form = EventForm(instance=event)

    return render(request, 'organizer/event_form.html', {
        'form': form,
        'event': event,
        'title': 'Edit Event',
    })


@login_required
def event_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    check_event_owner(request, event)

    certificates = Certificate.objects.filter(event=event)

    return render(request, 'organizer/event_detail.html',
        {'event': event, 'certificates': certificates, })


@login_required
def create_certificate(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    check_event_owner(request, event)

    if request.method == 'POST':
        form = CertificateForm(request.POST, request.FILES)
        if form.is_valid():
            certificate = form.save(commit=False)
            certificate.event = event
            certificate.save()
            return redirect('event_detail', event_id=event.id)
    else:
        form = CertificateForm()

    return render(request, 'organizer/certificate_form.html',
        {'form': form, 'event': event,}
    )


@login_required
def edit_certificate(request, certificate_id):
    certificate = get_object_or_404(Certificate, id=certificate_id)
    check_event_owner(request, certificate.event)

    if request.method == 'POST':
        form = CertificateForm(
            request.POST,
            request.FILES,
            instance=certificate
        )

        if form.is_valid():
            form.save()
            messages.success(request, 'Certificate updated successfully.')
            return redirect(
                'event_detail',
                event_id=certificate.event.id
            )
    else:
        form = CertificateForm(instance=certificate)

    return render(request, 'organizer/certificate_form.html', {
        'form': form,
        'certificate': certificate,
        'event': certificate.event,
        'title': 'Edit Certificate',
    })


@login_required
def test_certificate_generation(request, certificate_id):
    certificate = get_object_or_404(Certificate, id=certificate_id)
    check_event_owner(request, certificate.event)

    participants = Participant.objects.filter(certificate=certificate)

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        cm, success = generator.get_certificate(certificate.id, email)

        if success:
            return HttpResponse(cm.certificate_file, content_type='application/pdf')

        messages.error(request, 'Certificate generation failed or participant not found.')

    return render(request, 'organizer/test_certificate.html', 
        {'certificate': certificate, 'participants': participants,}
    )


@login_required
def publish_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    check_event_owner(request, event)

    event.publish()

    messages.success(request, 'Event published successfully.')
    return redirect('event_detail', event_id=event.id)


@login_required
def unpublish_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    check_event_owner(request, event)

    event.unpublish()

    messages.success(request, 'Event unpublished successfully.')
    return redirect('event_detail', event_id=event.id)

@login_required
def bulk_download_certificates(request, certificate_id):
    certificate = get_object_or_404(Certificate, id=certificate_id)
    check_event_owner(request, certificate.event)

    buffer = BytesIO()

    with zipfile.ZipFile(buffer, 'w') as zip_file:
        participants = Participant.objects.filter(certificate=certificate)

        for participant in participants:
            cm, success = generator.get_certificate(certificate.id, participant.email)
            if success and cm.certificate_file:
                zip_file.write(
                    cm.certificate_file.path,
                    arcname=f'{participant.email}.pdf'
                )

    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="certificates.zip"'
    return response


@login_required
def delete_participant(request, participant_id):
    participant = get_object_or_404(Participant, id=participant_id)
    certificate = participant.certificate
    check_event_owner(request, certificate.event)

    if request.method == 'POST':
        participant.delete()
        messages.success(request, 'Participant deleted successfully.')
        return redirect('participants', certificate_id=certificate.id)

    return render(request, 'organizer/participant_confirm_delete.html',
                  {'participant': participant, 'certificate': certificate,}
    )

@login_required
def edit_participant(request, participant_id):
    participant = get_object_or_404(Participant, id=participant_id)
    certificate = participant.certificate
    check_event_owner(request, certificate.event)

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        details_text = request.POST.get('details', '').strip()

        if not email:
            messages.warning(request, 'Email is required.')
            return render(request, 'organizer/participant_form.html', {
                'participant': participant,
                'certificate': certificate,
                'email': email,
                'details_text': details_text,
            })

        try:
            parsed_details = json.loads(details_text)
        except json.JSONDecodeError:
            messages.warning(request, 'Details must be valid JSON.')
            return render(request, 'organizer/participant_form.html', {
                'participant': participant,
                'certificate': certificate,
                'email': email,
                'details_text': details_text,
            })

        participant.email = email
        participant.details = parsed_details
        participant.save()

        CertificateManager.objects.filter(participant=participant).delete()

        messages.success(
            request,
            'Participant updated successfully. Certificate will be regenerated on next download.'
        )

        return redirect(
            'participants',
            certificate_id=certificate.id
        )

    details_text = json.dumps(participant.details or {}, indent=2)

    return render(request, 'organizer/participant_form.html', {
        'participant': participant,
        'certificate': certificate,
        'email': participant.email,
        'details_text': details_text,
    })


@login_required
def participants(request, certificate_id):
    certificate = get_object_or_404(Certificate, id=certificate_id)
    check_event_owner(request, certificate.event)

    participants = Participant.objects.filter(
        certificate=certificate
    ).order_by('email')

    participant_rows = []

    for participant in participants:
        details = participant.details or {}

        participant_rows.append({
            'participant': participant,
            'details': details,
            'name': details.get('name', ''),
        })

    return render(request, 'organizer/participants.html', {
        'certificate': certificate,
        'participant_rows': participant_rows,
    })
