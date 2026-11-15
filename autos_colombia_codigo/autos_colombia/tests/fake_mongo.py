"""MongoDB simulado en memoria con el subconjunto de la API de pymongo que usa el proyecto.
Solo sirve para las pruebas automáticas cuando no hay un servidor MongoDB disponible."""
import copy
import re

from datos.db import DuplicateKeyError


class _Res:
    def __init__(self, matched=0, modified=0):
        self.matched_count, self.modified_count = matched, modified


def _valor(doc, campo):
    return doc.get(campo)


def _cumple(doc, filtro):
    for k, v in filtro.items():
        if k == "$or":
            if not any(_cumple(doc, f) for f in v):
                return False
        elif k == "$and":
            if not all(_cumple(doc, f) for f in v):
                return False
        elif isinstance(v, dict) and v and all(x.startswith("$") for x in v):
            val = _valor(doc, k)
            for op, arg in v.items():
                if op == "$eq" and not val == arg: return False
                if op == "$ne" and not val != arg: return False
                if op == "$in" and val not in arg: return False
                if op == "$exists" and (k in doc) != arg: return False
                if op in ("$lt", "$lte", "$gt", "$gte"):
                    if val is None: return False
                    if op == "$lt" and not val < arg: return False
                    if op == "$lte" and not val <= arg: return False
                    if op == "$gt" and not val > arg: return False
                    if op == "$gte" and not val >= arg: return False
                if op == "$regex":
                    flags = re.I if "i" in v.get("$options", "") else 0
                    if not isinstance(val, str) or not re.search(arg, val, flags): return False
        else:
            if _valor(doc, k) != v:
                return False
    return True


def _aplicar(doc, upd):
    for op, campos in upd.items():
        for c, v in campos.items():
            if op == "$set": doc[c] = v
            elif op == "$inc": doc[c] = doc.get(c, 0) + v
            elif op == "$unset": doc.pop(c, None)
            else: raise NotImplementedError(op)


class _Cursor:
    def __init__(self, docs): self.docs = docs
    def sort(self, clave, direccion=1):
        pares = clave if isinstance(clave, list) else [(clave, direccion)]
        for c, d in reversed(pares):
            self.docs.sort(key=lambda x: (x.get(c) is None, x.get(c)), reverse=(d == -1))
        return self
    def __iter__(self): return iter(copy.deepcopy(self.docs))


class _Coleccion:
    def __init__(self):
        self.docs, self.indices, self._n = [], [], 0

    def create_index(self, claves, unique=False, partialFilterExpression=None):
        campo = claves if isinstance(claves, str) else claves[0][0]
        self.indices.append((campo, unique, partialFilterExpression))

    def _verificar(self, doc, excepto=None):
        for campo, unico, parcial in self.indices:
            if not unico or (parcial and not _cumple(doc, parcial)):
                continue
            for otro in self.docs:
                if otro is excepto or (parcial and not _cumple(otro, parcial)):
                    continue
                if otro.get(campo) == doc.get(campo):
                    raise DuplicateKeyError(f"duplicado en {campo}")

    def insert_one(self, doc):
        doc = copy.deepcopy(doc)
        self._n += 1
        doc.setdefault("_id", self._n)
        self._verificar(doc)
        self.docs.append(doc)

    def _buscar(self, filtro):
        return [d for d in self.docs if _cumple(d, filtro or {})]

    def find(self, filtro=None):
        return _Cursor(self._buscar(filtro))

    def find_one(self, filtro=None, sort=None):
        docs = _Cursor(self._buscar(filtro))
        if sort: docs.sort(sort)
        return copy.deepcopy(docs.docs[0]) if docs.docs else None

    def count_documents(self, filtro):
        return len(self._buscar(filtro))

    def _actualizar(self, filtro, upd, upsert, sort=None):
        docs = _Cursor(self._buscar(filtro))
        if sort: docs.sort(sort)
        if not docs.docs:
            if not upsert: return None
            nuevo = {k: v for k, v in filtro.items() if not k.startswith("$") and not isinstance(v, dict)}
            _aplicar(nuevo, upd); self.insert_one(nuevo)
            return self.docs[-1]
        doc = docs.docs[0]
        copia = copy.deepcopy(doc); _aplicar(copia, upd); self._verificar(copia, excepto=doc)
        doc.clear(); doc.update(copia)
        return doc

    def update_one(self, filtro, upd, upsert=False):
        d = self._actualizar(filtro, upd, upsert)
        return _Res(1 if d else 0, 1 if d else 0)

    def find_one_and_update(self, filtro, upd, sort=None, upsert=False, return_document=False):
        antes = None
        docs = _Cursor(self._buscar(filtro))
        if sort: docs.sort(sort)
        if docs.docs: antes = copy.deepcopy(docs.docs[0])
        d = self._actualizar(filtro, upd, upsert, sort)
        if d is None: return None
        return copy.deepcopy(d) if return_document else antes


class FakeDB:
    def __init__(self): self._c = {}
    def __getitem__(self, n): return self._c.setdefault(n, _Coleccion())
    __getattr__ = __getitem__
