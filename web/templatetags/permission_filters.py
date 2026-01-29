from django import template

register = template.Library()

ACTION_TRANSLATIONS = {
	'add': 'Crear',
	'change': 'Editar',
	'delete': 'Eliminar',
	'view': 'Ver',
}

# Overrides opcionales por si necesitas traducir algo concreto distinto
PERMISSION_OVERRIDES = {
	# 'add_custommodel': 'Texto personalizado',
}


def _humanize_model_name(model):
	if not model:
		return ''
	try:
		return model._meta.verbose_name
	except Exception:
		return str(model)


@register.filter
def translate_permission(permission_name):
	"""Traduce dinámicamente: acción + verbose_name del modelo."""

	perm_obj = permission_name if hasattr(permission_name, 'codename') else None

	if perm_obj:
		perm_code = perm_obj.codename.lower()
	else:
		perm_code = str(permission_name).split('|')[0].strip().lower()

	if perm_code in PERMISSION_OVERRIDES:
		return PERMISSION_OVERRIDES[perm_code]

	try:
		action, model_code = perm_code.split('_', 1)
	except ValueError:
		return permission_name

	action_es = ACTION_TRANSLATIONS.get(action, action)

	model_verbose = model_code.replace('_', ' ')
	if perm_obj and hasattr(perm_obj, 'content_type'):
		model_class = perm_obj.content_type.model_class()
		verbose = _humanize_model_name(model_class)
		if verbose:
			model_verbose = verbose

	return f"{action_es} {model_verbose}"

