"""Template tags spécifiques au back-office KAYDAN SHIELD."""
from django import template

register = template.Library()


@register.filter(name="has_perm")
def has_perm(user_perms, code):
    """Vérifie si user_perms contient `code`, `"*"` ou `module.*`.

    Usage template :
        {% if user_perms|has_perm:"employees.view" %}
          <a>...</a>
        {% endif %}

    `user_perms` est injecté par AdminContextMixin et BaseAdminView.
    Pour un super-admin → {"*"} → match tout.
    Pour un user lambda → {"employees.view", "badges.view"} → match exact + wildcards.
    """
    if not user_perms:
        return False
    if "*" in user_perms:
        return True
    if code in user_perms:
        return True
    # Wildcard module : "employees.*" couvre "employees.view"
    if "." in code:
        module_wildcard = code.split(".", 1)[0] + ".*"
        if module_wildcard in user_perms:
            return True
    return False


@register.filter(name="has_any_perm")
def has_any_perm(user_perms, codes):
    """Vérifie si user_perms a AU MOINS UNE des permissions (csv).

    Usage : {% if user_perms|has_any_perm:"reports.view,reports.run" %}
    """
    if not user_perms or not codes:
        return False
    for c in codes.split(","):
        if has_perm(user_perms, c.strip()):
            return True
    return False


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
