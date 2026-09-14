from django.db import migrations


SYSTEM_ROLE_GROUPS = ("reviewer", "operator")


def create_system_role_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in SYSTEM_ROLE_GROUPS:
        Group.objects.get_or_create(name=name)


def delete_system_role_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=SYSTEM_ROLE_GROUPS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(
            create_system_role_groups,
            reverse_code=delete_system_role_groups,
        ),
    ]
