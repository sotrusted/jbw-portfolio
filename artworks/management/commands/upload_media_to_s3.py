"""Copy every image the database refers to from the local media/ folder into the S3 bucket.

    AWS_STORAGE_BUCKET_NAME=my-bucket python manage.py upload_media_to_s3

Keys match the paths stored in the database, so the site works unchanged once it points at the
bucket. Files already in the bucket with the same size are skipped, so this is safe to re-run.
"""
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import ImageField

from artworks.models import Artwork, Bio, SeriesTile


class Command(BaseCommand):
    help = 'Upload all database-referenced media files to the configured S3 bucket.'

    def handle(self, *args, **options):
        bucket = settings.AWS_STORAGE_BUCKET_NAME
        if not bucket:
            raise CommandError('Set AWS_STORAGE_BUCKET_NAME first.')
        names = set()
        for model in (Artwork, SeriesTile, Bio):
            fields = [f.name for f in model._meta.fields if isinstance(f, ImageField)]
            for row in model.objects.values_list(*fields):
                names.update(name for name in row if name)

        client = boto3.client('s3', region_name=settings.AWS_S3_REGION_NAME)
        existing = {}
        for page in client.get_paginator('list_objects_v2').paginate(Bucket=bucket):
            existing.update({obj['Key']: obj['Size'] for obj in page.get('Contents', [])})

        media_root = Path(settings.BASE_DIR) / 'media'
        todo, missing = [], []
        for name in sorted(names):
            path = media_root / name
            if not path.exists():
                missing.append(name)
            elif existing.get(name) != path.stat().st_size:
                todo.append((name, path))
        self.stdout.write(f'{len(names)} files referenced, {len(names) - len(todo) - len(missing)} already uploaded, '
                          f'{len(todo)} to upload')

        def upload(item):
            name, path = item
            client.upload_file(str(path), bucket, name, ExtraArgs={
                'ContentType': mimetypes.guess_type(name)[0] or 'application/octet-stream',
                **settings.AWS_S3_OBJECT_PARAMETERS,
            })

        with ThreadPoolExecutor(max_workers=8) as pool:
            for done, _ in enumerate(pool.map(upload, todo), start=1):
                if done % 200 == 0:
                    self.stdout.write(f'  {done}/{len(todo)}')
        if missing:
            self.stdout.write(self.style.WARNING(f'Not found locally: {", ".join(missing[:10])}'))
        self.stdout.write(self.style.SUCCESS(f'Uploaded {len(todo)} files to s3://{bucket}'))
