import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def move_oidc_identities_and_create_profiles(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    UserProfile = apps.get_model("accounts", "UserProfile")
    ExternalIdentity = apps.get_model("accounts", "ExternalIdentity")

    for profile in UserProfile.objects.all().iterator():
        provider = (
            "google"
            if profile.oidc_issuer == "https://accounts.google.com"
            else "oidc"
        )
        ExternalIdentity.objects.create(
            user_id=profile.user_id,
            provider=provider,
            issuer=profile.oidc_issuer,
            subject=profile.oidc_subject,
            email=profile.user.email,
        )

    existing_user_ids = set(
        UserProfile.objects.values_list("user_id", flat=True)
    )
    UserProfile.objects.bulk_create(
        UserProfile(user_id=user_id)
        for user_id in User.objects.exclude(pk__in=existing_user_ids).values_list(
            "pk", flat=True
        )
    )


def restore_oidc_fields(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    ExternalIdentity = apps.get_model("accounts", "ExternalIdentity")

    for identity in ExternalIdentity.objects.order_by("created_at").iterator():
        UserProfile.objects.filter(user_id=identity.user_id).update(
            oidc_issuer=identity.issuer,
            oidc_subject=identity.subject,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_system_role_groups"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExternalIdentity",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("provider", models.SlugField(max_length=50)),
                ("issuer", models.URLField(max_length=512)),
                ("subject", models.CharField(max_length=255)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="external_identities",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["provider"],
                        name="accounts_identity_provider_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("issuer", "subject"),
                        name="accounts_identity_unique_issuer_subject",
                    )
                ],
            },
        ),
        migrations.RunPython(
            move_oidc_identities_and_create_profiles,
            restore_oidc_fields,
        ),
        migrations.RemoveConstraint(
            model_name="userprofile",
            name="accounts_profile_unique_oidc_identity",
        ),
        migrations.RemoveField(
            model_name="userprofile",
            name="oidc_issuer",
        ),
        migrations.RemoveField(
            model_name="userprofile",
            name="oidc_subject",
        ),
    ]
