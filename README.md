# Best Dressed · Western Rodeo

Página de votación compartida para elegir al mejor vestido masculino y a la mejor vestida femenina. Tiene interfaz móvil, selección de una persona por categoría, confirmación antes de enviar, registro en SQLite, límite de una papeleta por navegador, panel privado, resultados ocultos para el público y exportación CSV.

## Ejecutar en tu computador

Requiere Python 3.10 o posterior. No necesita instalar librerías externas.

1. Descomprime la carpeta en tu computador.
2. Abre Terminal dentro de la carpeta `rodeo-votacion`.
3. Ejecuta:

   ```bash
   python3 app.py
   ```

4. Abre `http://localhost:8080` para ver la página de votación.
5. Abre `http://localhost:8080/admin` para preparar la lista de invitados.
6. La contraseña inicial del panel local es `RodeoAdmin2026!`.
7. En el panel agrega los nombres y las fotos, y pulsa **Guardar participantes**.

Para detener el servidor, vuelve a la Terminal y pulsa `Ctrl+C`.

## Publicar para que voten todos los invitados

El modo local sirve para probar la página en tu computador. Para que los invitados accedan por un enlace o QR desde sus propios teléfonos, esta carpeta debe desplegarse en un servicio de hosting que ejecute Python y permita conservar archivos persistentes. La base de datos se guarda en `data/voting.sqlite3` (o dentro de la carpeta indicada por `DATA_DIR`). Configura estas variables de entorno en el hosting:

- `ADMIN_PASSWORD`: una contraseña privada y fuerte para el panel. No uses la contraseña temporal incluida.
- `SECURE_COOKIE=1`: activa la cookie segura cuando el sitio está publicado mediante HTTPS.
- `PORT`: normalmente lo define automáticamente el servicio de hosting.
- `DATA_DIR`: opcional; ruta de un volumen/almacenamiento persistente para `voting.sqlite3`.

El hosting debe usar HTTPS y conservar la base de datos entre reinicios. No publiques la página en un hosting estático, porque necesita el servidor `app.py` para registrar y compartir los votos. Una vez publicada, comparte la URL pública o conviértela en un código QR.

## Cómo se configura

- Entra a `/admin` y agrega cada persona a la categoría correspondiente.
- Puedes subir fotos JPG, PNG, WEBP o GIF de hasta 5 MB desde tu dispositivo, o pegar una URL de imagen.
- En cada papeleta, el invitado elige un hombre y una mujer; antes de enviar puede revisar la selección.
- Los resultados y el CSV solo están disponibles tras autenticarse en el panel organizador.
- El panel incluye una opción para borrar todos los votos si necesitas comenzar de nuevo.

## Privacidad y límite de voto

La papeleta no pide nombre, correo ni teléfono. La aplicación no guarda direcciones IP y no escribe solicitudes en un registro de acceso. Para limitar votos repetidos, guarda una cookie aleatoria en el navegador y un hash de esa cookie junto con las selecciones; la cookie no está vinculada al nombre de la persona. Por eso, el límite real es **una papeleta por navegador/cookie**, no una verificación de identidad: si alguien borra las cookies o usa otro navegador o dispositivo podría volver a votar. Bloquear absolutamente el voto duplicado por persona requiere un método adicional de verificación, que afecta al anonimato.

Los votos guardan una copia del nombre elegido al momento de enviar la papeleta, así el historial no se pierde si el organizador después modifica el listado. El CSV contiene las elecciones y la fecha de registro, no la identidad del votante ni su IP.
