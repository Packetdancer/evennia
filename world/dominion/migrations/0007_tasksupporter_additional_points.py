# -*- coding: utf-8 -*-
# Generated by Django 1.9.9 on 2017-02-09 02:08
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dominion', '0006_auto_20170201_0444'),
    ]

    operations = [
        migrations.AddField(
            model_name='tasksupporter',
            name='additional_points',
            field=models.PositiveSmallIntegerField(blank=0, default=0),
        ),
    ]
