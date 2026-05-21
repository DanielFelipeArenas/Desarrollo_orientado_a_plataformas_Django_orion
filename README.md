# DOAPG4-Orion
Este proyecto es una solución integral para la gestión y administración de bibliotecas, diseñada para optimizar el control de inventario de libros y el flujo de transacciones con los usuarios. El sistema permite automatizar las tareas cotidianas de una biblioteca, garantizando la integridad de la información y facilitando la toma de decisiones.

## Funcionalidades Principales
El sistema está estructurado en torno a cinco módulos clave:

Gestión de Libros: Control total sobre el catálogo bibliográfico (altas, bajas, ediciones y consultas de stock).

Préstamos: Registro detallado de la salida de ejemplares, vinculando libros con usuarios y fechas estimadas de entrega.

Devoluciones: Procesamiento de ingresos de libros al sistema, actualizando automáticamente la disponibilidad en el inventario.

Historial: Registro cronológico de todas las transacciones realizadas, permitiendo auditorías y seguimiento de movimientos pasados.

Multas y Sanciones: Sistema automático (o manual) para la gestión de recargos económicos o administrativos por entregas tardías.

## Tecnologías Usadas

Lenguaje: Python

Base de Datos: SQLite

Framework: Django

## Ejecución local en Windows

Este proyecto puede iniciarse sin escribir comandos manuales usando [start_project.bat](start_project.bat).

Pasos recomendados para un clon limpio:

1. Asegurarse de tener Python instalado en Windows.
2. Ejecutar [start_project.bat](start_project.bat).
3. El script crea `.venv` si no existe e instala Django desde `requirements.txt`.
4. Elegir `Crear superusuario` la primera vez.
5. Entrar a `/admin/` y cargar administradores, usuarios y libros.
6. Volver a ejecutar el `.bat` y elegir `Iniciar servidor`.

# Guía de presentación del proyecto

## 1. Nombre del proyecto

Orion's Library.

## 2. Integrantes del grupo

Completar con los nombres reales del equipo y el rol de cada uno.

## 3. Rol o aporte de cada integrante

Indicar quién hizo frontend, backend, base de datos, pruebas, documentación o diseño.

## 4. Objetivo general del proyecto

Digitalizar la gestión de una biblioteca con control de libros, usuarios, préstamos, multas e historial.

## 5. Objetivos específicos

- Registrar y administrar libros, usuarios y préstamos.
- Controlar devoluciones y atrasos.
- Gestionar multas y mantener historial de acciones.

## 6. Descripción general del proyecto

Es una aplicación web para administrar operaciones básicas de biblioteca desde una interfaz centralizada.

## 7. Aplicaciones en la vida cotidiana

Puede usarse en bibliotecas escolares, comunitarias o pequeñas instituciones que necesiten control de inventario y préstamos.

## 8. Alcance del proyecto

Incluye gestión de libros, usuarios, préstamos, multas, historial y búsqueda. No incluye autenticación avanzada por roles, despliegue en nube ni reportes complejos.

## 9. Tecnología usada

- Python: lenguaje principal.
- Django: framework web y lógica del sistema.
- SQLite: base de datos local.
- HTML/CSS: interfaz visual.
- Bootstrap y Font Awesome: componentes visuales e iconos.

## 10. Arquitectura general del sistema

Frontend en plantillas HTML, backend en vistas Django, persistencia en SQLite y configuración central en el proyecto `DOAPG4_Orion`.

## 11. Manejo de errores

El sistema valida acceso con `login_required`, evita acciones sin sesión y restringe operaciones de escritura a `POST`.

## 12. Seguridad implementada

Autenticación con Django, protección de rutas, CSRF en formularios y bloqueo de operaciones sensibles fuera de `POST`.

## 13. Despliegue o entorno de ejecución

El proyecto funciona en local con Django y SQLite; no requiere nube ni Docker para la demostración.

## Integrantes
Daniel Felipe Arenas Gómez
Jose David Baron Perez
Astrid Jhoana Inocencio Duarte
Darcy Tatiana Escalante Garcia
