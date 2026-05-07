"""Template tags spécifiques au back-office KAYDAN SHIELD."""
from django import template

register = template.Library()


@register.simple_tag
def qs_replace(request, **kwargs):
    """Renvoie une querystring où les `kwargs` remplacent / ajoutent les
    valeurs courantes de `request.GET`.

    Exemple :
        {% qs_replace request page=2 %}
        # ?q=foo&f=active → q=foo&f=active&page=2

    Idéal pour les liens de pagination qui doivent préserver q, f, etc.
    """
    if not request:
        return ""
    new_qd = request.GET.copy()
    for key, value in kwargs.items():
        if value is None or value == "":
            new_qd.pop(key, None)
        else:
            new_qd[key] = str(value)
    return new_qd.urlencode()
