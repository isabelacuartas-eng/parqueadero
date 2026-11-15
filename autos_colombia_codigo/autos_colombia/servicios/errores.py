"""Excepción común de las reglas de negocio."""


class ReglaNegocioError(Exception):
    """Se lanza cuando una operación incumple una regla de negocio."""
