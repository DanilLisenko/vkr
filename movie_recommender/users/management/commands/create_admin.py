from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Создает администратора сайта (is_admin=True)'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='admin', help='Логин (по умолчанию: admin)')
        parser.add_argument('--password', default='Admin1234!', help='Пароль (по умолчанию: Admin1234!)')
        parser.add_argument('--email', default='admin@example.com', help='Email')

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']
        email = options['email']

        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': email},
        )

        user.set_password(password)
        user.is_admin = True
        user.is_active = True
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(
                f'Администратор создан: {username} / {password}'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Администратор обновлён: {username} / {password}'
            ))
