from django.db import migrations

CATEGORIES = [
    ("Music & Concerts", "music", "music"),
    ("Church & Gospel", "church-gospel", "church"),
    ("Conferences & Business", "business", "briefcase"),
    ("Parties & Nightlife", "nightlife", "party"),
    ("Comedy", "comedy", "smile"),
    ("Arts & Culture", "arts-culture", "palette"),
    ("Festivals", "festivals", "flag"),
    ("Sports & Fitness", "sports", "trophy"),
    ("Education & Schools", "education", "school"),
    ("Tech", "tech", "cpu"),
    ("Food & Drink", "food-drink", "utensils"),
    ("Fashion & Beauty", "fashion", "shirt"),
    ("Film & Theatre", "film-theatre", "film"),
    ("Charity & Causes", "charity", "heart"),
    ("Funerals & Memorials", "funerals-memorials", "flower"),
    ("Weddings & Celebrations", "celebrations", "rings"),
    ("Other", "other", "tag"),
]


def seed(apps, schema_editor):
    Category = apps.get_model("events", "Category")
    for i, (name, slug, icon) in enumerate(CATEGORIES):
        Category.objects.get_or_create(slug=slug, defaults={"name": name, "icon": icon, "sort_order": i})


def unseed(apps, schema_editor):
    apps.get_model("events", "Category").objects.filter(slug__in=[c[1] for c in CATEGORIES]).delete()


class Migration(migrations.Migration):
    dependencies = [("events", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
