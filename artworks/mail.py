"""Sending enquiries from the contact form.

Delivery goes through Resend's SMTP relay (see settings). The visitor's address is used as
Reply-To rather than From, so Joseph can simply hit reply, and so the message passes SPF.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMessage

from .models import Bio

logger = logging.getLogger(__name__)


def recipient():
    """Joseph's address, taken from the Information page unless one is configured explicitly."""
    if settings.CONTACT_TO_EMAIL:
        return settings.CONTACT_TO_EMAIL
    bio = Bio.objects.first()
    return bio.email if bio and bio.email else ''


def send_enquiry(enquiry):
    """Email one enquiry. Returns True if it was accepted for delivery."""
    to = recipient()
    if not to:
        logger.error('Enquiry %s not sent: no recipient address set', enquiry.pk)
        return False
    body = (
        f'{enquiry.name} <{enquiry.email}> wrote through josephbochettowalsh.com:\n\n'
        f'{enquiry.message}\n\n'
        f'--\nReply to this email to answer them directly.'
    )
    email = EmailMessage(
        subject=f'Website enquiry from {enquiry.name}',
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to],
        reply_to=[enquiry.email],
    )
    try:
        sent = email.send(fail_silently=False)
    except Exception:  # a delivery problem must never lose the message or break the page
        logger.exception('Enquiry %s could not be emailed', enquiry.pk)
        return False
    return bool(sent)
