from django.db import models


class GhanaRegion(models.TextChoices):
    AHAFO = "ahafo", "Ahafo"
    ASHANTI = "ashanti", "Ashanti"
    BONO = "bono", "Bono"
    BONO_EAST = "bono_east", "Bono East"
    CENTRAL = "central", "Central"
    EASTERN = "eastern", "Eastern"
    GREATER_ACCRA = "greater_accra", "Greater Accra"
    NORTH_EAST = "north_east", "North East"
    NORTHERN = "northern", "Northern"
    OTI = "oti", "Oti"
    SAVANNAH = "savannah", "Savannah"
    UPPER_EAST = "upper_east", "Upper East"
    UPPER_WEST = "upper_west", "Upper West"
    VOLTA = "volta", "Volta"
    WESTERN = "western", "Western"
    WESTERN_NORTH = "western_north", "Western North"


class MobileMoneyProvider(models.TextChoices):
    MTN = "mtn", "MTN MoMo"
    TELECEL = "telecel", "Telecel Cash"
    AIRTELTIGO = "airteltigo", "AT Money"
