# Generated manually for reader portal features

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('biblioteca', '0002_configuracion_empleado_activo_usuario_activo_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='usuario',
            name='user',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='perfil_lector',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name='ReservaLibro',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_reserva', models.DateTimeField(auto_now_add=True)),
                ('fecha_apartado', models.DateTimeField(blank=True, null=True)),
                ('fecha_expiracion', models.DateTimeField(blank=True, null=True)),
                ('estado', models.CharField(choices=[('En cola', 'En cola'), ('Apartado', 'Apartado'), ('Convertido', 'Convertido a prestamo'), ('Cancelado', 'Cancelado'), ('Vencido', 'Vencido')], default='En cola', max_length=20)),
                ('libro', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reservas', to='biblioteca.libro')),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reservas', to='biblioteca.usuario')),
            ],
            options={
                'ordering': ['fecha_reserva'],
            },
        ),
        migrations.CreateModel(
            name='ValoracionLibro',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('puntaje', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ('comentario', models.TextField(blank=True, null=True)),
                ('fecha', models.DateTimeField(auto_now=True)),
                ('libro', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='valoraciones', to='biblioteca.libro')),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='valoraciones', to='biblioteca.usuario')),
            ],
            options={
                'verbose_name': 'Valoracion de libro',
                'verbose_name_plural': 'Valoraciones de libros',
                'unique_together': {('usuario', 'libro')},
            },
        ),
    ]
