import itertools
import re

import requests
from django.db.models import Q

from .models import Autor, Genero, Libro


class GoogleBooksService:
    """
    Servicio de integracion con Open Library API.
    El nombre se conserva para no romper imports existentes.
    """

    BASE_URL = "https://openlibrary.org/search.json"
    HEADERS = {'User-Agent': 'BibliotecaUniversitaria/1.0 (contacto@biblioteca.edu.co)'}
    TEMAS_VARIADOS = [
        "literatura clasica",
        "historia universal",
        "ciencia",
        "filosofia",
        "arte",
        "biologia",
        "matematicas",
        "tecnologia",
        "novela",
        "psicologia",
        "economia",
        "educacion",
    ]

    @staticmethod
    def _normalizar(texto):
        return re.sub(r"\s+", " ", (texto or "").strip().lower())

    @staticmethod
    def _queries(query):
        if not query or query.lower() in {"variado", "varios", "todos", "general"}:
            return GoogleBooksService.TEMAS_VARIADOS
        return [query]

    @staticmethod
    def _doc_duplicado(doc):
        ol_id = doc.get("key", "").split("/")[-1]
        titulo = GoogleBooksService._normalizar(doc.get("title", ""))
        autores = [GoogleBooksService._normalizar(a) for a in doc.get("author_name", [])]
        isbn_list = [isbn for isbn in doc.get("isbn", []) if isbn]

        filtros = Q()
        if ol_id:
            filtros |= Q(google_volume_id=ol_id)
        for isbn in isbn_list[:5]:
            filtros |= Q(isbn_10=isbn[:20]) | Q(isbn_13=isbn[:20])
        if filtros and Libro.objects.filter(filtros).exists():
            return True

        if titulo:
            existentes = Libro.objects.filter(titulo__iexact=doc.get("title", "")).prefetch_related('autores')
            for libro in existentes:
                autores_existentes = {
                    GoogleBooksService._normalizar(autor.nombre)
                    for autor in libro.autores.all()
                }
                if not autores or autores_existentes.intersection(autores):
                    return True
        return False

    @staticmethod
    def _crear_libro_desde_doc(doc, query):
        ol_id = doc.get("key", "").split("/")[-1]
        if not ol_id or GoogleBooksService._doc_duplicado(doc):
            return None

        isbn_list = doc.get("isbn", [])
        isbn_10 = next((isbn for isbn in isbn_list if len(isbn) == 10), "")
        isbn_13 = next((isbn for isbn in isbn_list if len(isbn) == 13), "")
        if not isbn_13:
            isbn_13 = isbn_list[0][:13] if isbn_list else f"S-ISBN-{ol_id[:10]}"

        editorial_raw = doc.get("publisher")
        editorial = editorial_raw[0][:200] if editorial_raw else "Editorial generica"
        idiomas = doc.get("language") or []

        libro = Libro.objects.create(
            google_volume_id=ol_id,
            titulo=doc.get("title", "Sin titulo")[:255],
            editorial=editorial,
            fecha_publicacion=str(doc.get("first_publish_year", "2024")),
            descripcion=f"Libro sobre {query} importado de Open Library.",
            cantidad_paginas=doc.get("number_of_pages_median") or 100,
            idioma=(idiomas[0] if idiomas else "es")[:10],
            isbn_10=isbn_10[:20],
            isbn_13=isbn_13[:20],
            portada_url=(
                f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-M.jpg"
                if doc.get('cover_i') else ""
            ),
            cantidad_disponible=10,
            cantidad_total=10,
        )

        for nombre_autor in doc.get("author_name", ["Autor anonimo"]):
            autor, _ = Autor.objects.get_or_create(nombre=nombre_autor[:255])
            libro.autores.add(autor)

        # Open Library trae materias en "subject"; las usamos como generos.
        generos = doc.get("subject") or doc.get("subject_facet") or []
        if not generos:
            generos = [query.title()]
        for nombre_genero in generos[:4]:
            genero, _ = Genero.objects.get_or_create(nombre=nombre_genero[:255])
            libro.generos.add(genero)

        return libro

    @staticmethod
    def _consultar_docs(tema, objetivo):
        params = {
            "q": tema,
            "limit": min(max(objetivo * 3, 10), 50),
            "fields": (
                "key,title,author_name,isbn,publisher,first_publish_year,"
                "number_of_pages_median,cover_i,subject,subject_facet,language"
            ),
        }
        response = requests.get(
            GoogleBooksService.BASE_URL,
            params=params,
            headers=GoogleBooksService.HEADERS,
            timeout=15,
        )
        if response.status_code != 200:
            print(f"[Open Library] Error HTTP {response.status_code}")
            return []
        return response.json().get("docs", [])

    @staticmethod
    def _importar(query, cantidad):
        libros_creados = 0
        queries = GoogleBooksService._queries(query)
        intentos_sin_crear = 0
        max_intentos = max(len(queries) * 2, 4)

        for tema in itertools.cycle(queries):
            if libros_creados >= cantidad or intentos_sin_crear >= max_intentos:
                break

            creados_en_tema = 0
            try:
                docs = GoogleBooksService._consultar_docs(tema, cantidad - libros_creados)
                for doc in docs:
                    if libros_creados >= cantidad:
                        break
                    libro = GoogleBooksService._crear_libro_desde_doc(doc, tema)
                    if libro:
                        libros_creados += 1
                        creados_en_tema += 1
                        print(f"[Open Library] Guardado: {libro.titulo}")
            except Exception as exc:
                print(f"[Open Library] Error: {exc}")

            if len(queries) == 1:
                break
            intentos_sin_crear = intentos_sin_crear + 1 if creados_en_tema == 0 else 0

        return libros_creados

    @staticmethod
    def poblar_biblioteca(query="variado", limite_total=100):
        conteo_actual = Libro.objects.count()
        if conteo_actual >= limite_total:
            return 0
        return GoogleBooksService._importar(query, limite_total - conteo_actual)

    @staticmethod
    def solicitar_mas_libros(query="variado", cantidad=20):
        return GoogleBooksService._importar(query, cantidad)
