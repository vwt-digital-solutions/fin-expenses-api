import ast
from flask import make_response, jsonify


def make_response_translated(message, http_code):
    error_translations = {
        "Geen overeenkomst op e-mail": {
            "nl": "Geen overeenkomst op e-mail",
            "en": "No match on email",
            "de": "Keine Übereinstimmung per E-Mail"
        },
        "Geen overeenkomst op leasecoordinator": {
            "nl": "Geen overeenkomst op leasecoordinator",
            "en": "No match on lease coordinator",
            "de": "Keine Übereinstimmung mit dem Leasingkoordinator"
        },
        "Geen overeenkomst op manager e-mail": {
            "nl": "Geen overeenkomst op manager e-mail",
            "en": "No match on manager email",
            "de": "Keine Übereinstimmung in der Manager-E-Mail"
        },
        "Declaratie niet gevonden": {
            "nl": "Declaratie niet gevonden",
            "en": "Expense not found",
            "de": "Spesenabrechnung nicht gefunden"
        },
        "Ongeautoriseerd": {
            "nl": "Ongeautoriseerd",
            "en": "Unauthorized",
            "de": "Nicht autorisiert"
        },
        "Startdatum is later dan einddatum": {
            "nl": "Startdatum is later dan einddatum",
            "en": "Start date is later than end date",
            "de": "Das Startdatum liegt nach dem Enddatum"
        },
        "Geen geldige queryparameter": {
            "nl": "Geen geldige queryparameter",
            "en": "Not a valid query parameter",
            "de": "Kein gültiger Abfrageparameter"
        },
        "Document niet gevonden": {
            "nl": "Document niet gevonden",
            "en": "Document not found",
            "de": "Dokument nicht gefunden"
        },
        "Er ging iets fout": {
            "nl": "Er ging iets fout",
            "en": "Something went wrong",
            "de": "Etwas ist schief gelaufen"
        },
        "Sommige gegevens ontbraken of waren onjuist": {
            "nl": "Sommige gegevens ontbraken of waren onjuist",
            "en": "Some data was missing or incorrect",
            "de": "Einige Daten fehlten oder waren falsch"
        },
        "Geen exports beschikbaar": {
            "nl": "Geen exports beschikbaar",
            "en": "No exports available",
            "de": "Keine Exporte verfügbar"
        },
        "Kan boekingsdossier niet uploaden": {
            "nl": "Kan boekingsdossier niet uploaden",
            "en": "Failed to upload booking file",
            "de": "Buchungsdatei konnte nicht hochgeladen werden"
        },
        "Kan betalingsbestand niet uploaden": {
            "nl": "Kan betalingsbestand niet uploaden",
            "en": "Failed to upload payment file",
            "de": "Zahlungsdatei konnte nicht hochgeladen werden"
        },
        "Kan boekingsdossier en betalingsbestand niet uploaden": {
            "nl": "Kan boekingsdossier en betalingsbestand niet uploaden",
            "en": "Failed to upload booking and payment files",
            "de": "Fehler beim Hochladen der Buchungs- und Zahlungsdateien"
        },
        "De inhoud van deze methode is niet geldig": {
            "nl": "De inhoud van deze methode is niet geldig",
            "en": "The content of this method is not valid",
            "de": "Der Inhalt dieser Methode ist ungültig"
        },
        "Verzoek mist een Accept-header": {
            "nl": "Verzoek mist een Accept-header",
            "en": "Request missing an Accept header",
            "de": "Anforderung fehlt ein Accept-Header"
        },
        "De declaratie moet minimaal één bijlage hebben": {
            "nl": "De declaratie moet minimaal één bijlage hebben",
            "en": "The expense must have at least one attachment",
            "de": "Die spesenabrechnung müssen mindestens einen Anhang enthalten"
        },
        "Dit account is niet meer actief": {
            "nl": "Dit account is niet meer actief",
            "en": "This account is no longer active",
            "de": "Dieses Konto ist nicht mehr aktiv"
        },
        "Het indienen van een declaratie is niet toegestaan tijdens het aanpassen van velden": {
            "nl": "Het indienen van een declaratie is niet toegestaan tijdens het aanpassen van velden",
            "en": "The submission of an expense is not authorized while modifying fields",
            "de": "Die Abgabe einer spesenabrechnung ist beim Ändern von Feldern nicht gestattet"
        },
        "Geen geldige kostensoort": {
            "nl": "Geen geldige kostensoort",
            "en": "Not a valid cost-type",
            "de": "Keine gültige Kostenart"
        },
        "Uw bankrekeningnummer (IBAN) is niet bekend in de personeelsadministratie": {
            "nl": "Uw bankrekeningnummer (IBAN) is niet bekend in de personeelsadministratie",
            "en": "Your bank account number (IBAN) is not found in the personnel administration",
            "de": "Ihre Bankkontonummer (IBAN) wird in der Personalverwaltung nicht gefunden"
        },
        "Medewerker niet gevonden": {
            "nl": "Medewerker niet gevonden",
            "en": "Employee not found",
            "de": "Mitarbeiter nicht gefunden"
        },
        "Medewerker niet uniek": {
            "nl": "Medewerker niet uniek",
            "en": "Employee not unique",
            "de": "Mitarbeiter nicht eindeutig"
        },
        "Medewerker heeft onvoldoende gegevens in de personeelsadministratie": {
            "nl": "Medewerker heeft onvoldoende gegevens in de personeelsadministratie",
            "en": "Employee has insufficient data in the personnel administration",
            "de": "Mitarbeiter verfügt über unzureichende Daten in der Personalverwaltung"
        },
        "Geen geldige afwijzing": {
            "nl": "Geen geldige afwijzing",
            "en": "Not a valid rejection",
            "de": "Keine gültige Ablehnung"
        },
        "Het declaratiebedrag moet hoger zijn dan €{},-": {
            "nl": "Het declaratiebedrag moet hoger zijn dan €{},-",
            "en": "The expense amount must be higher than €{},-",
            "de": "Der Kostenbetrag muss höher als €{},- sein"
        }
    }

    try:
        message_obj = ast.literal_eval(message)
        message = message_obj.get('message', 'Er ging iets fout')
        detail = error_translations.get(message, {})

        if 'replacements' in message_obj:
            message = message.format(*message_obj['replacements'])
            for lan in detail:
                detail[lan] = detail[lan].format(*message_obj['replacements'])
    except Exception:
        detail = error_translations.get(message, {})

    translated_response = {
        "detail": detail,
        "status": http_code,
        "title": message
    }

    return make_response(jsonify(translated_response), http_code)
