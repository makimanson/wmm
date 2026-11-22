<!--
SPDX-FileCopyrightText: 2026 makimanson
SPDX-License-Identifier: GPL-3.0-or-later

WMM - Wallpaper Multi-Monitor Manager

HELP_es.md -- Archivo de ayuda en castellano

WMM-Title: Ayuda
WMM-Contents: Contenidos
-->

# Entornos de escritorio

WMM dispone actualmente de integración completa con **Cinnamon**, **GNOME Shell**, **KDE Plasma 6**, **MATE**, **XFCE** y **Windows 11**.

El panel de control y las funciones principales son comunes a todos los entornos. Algunos controles pueden cambiar ligeramente de aspecto o ubicación según el escritorio, pero comparten la misma configuración.

# Ajustes

Abre el menú de WMM desde su icono en el panel o en la bandeja del sistema y selecciona **Ajustes** para abrir el panel de control.

## Opciones

Reúne la configuración general de WMM en cuatro grupos: **Cambiar el fondo de pantalla al iniciar**, **Modo Panorámico**, **Presentación de diapositivas** y **Metadatos de imagen**.

Cada grupo puede plegarse o desplegarse pulsando sobre su título. El interruptor situado a la derecha activa o desactiva la función correspondiente, independientemente de si sus controles están visibles. WMM recuerda el estado de despliegue de las secciones.

### Icono Ayuda

Abre esta ayuda en una ventana independiente.

### Icono Visor de Logs

Abre el visor de logs de depuración en una ventana aparte. Muestra la actividad de WMM y permite filtrar el registro.

### Icono Reiniciar

Reinicia el motor y el panel de control para volver a cargar WMM durante la sesión.

### Icono Plegar / Expandir

Pliega la columna lateral del panel para dejar más espacio a **Monitores** y **Miniaturas**. Al volver a pulsarlo se recupera la vista completa. WMM recuerda el estado del panel.

### Cambiar el fondo de pantalla al iniciar

El interruptor de la cabecera decide qué sucede al arrancar WMM:

- **Activado**: el motor selecciona imágenes nuevas y genera una nueva composición.
- **Desactivado**: se conserva la última composición guardada.

Los tres controles situados bajo esta cabecera son independientes de ese interruptor y también pueden utilizarse cuando está desactivado.

#### Selección por orientación del monitor

- **Activada**: WMM selecciona imágenes que coinciden con la orientación horizontal o vertical del monitor.
- **Desactivada**: pueden utilizarse imágenes de cualquier orientación.

Este filtro interviene en la selección de imágenes, pero no fuerza por sí solo un cambio de fondo.

#### Rotación selectiva

Permite limitar la rotación automática a las carpetas que hayas marcado expresamente en **Fuentes de imagen**.

Para preparar la selección, haz clic derecho sobre una carpeta activa y elige **Añadir a rotación selectiva**. La opción **Eliminar de rotación selectiva** retira su marca. Marcar carpetas no activa por sí solo el modo.

- **Activada**: la rotación utiliza las carpetas activas y marcadas para la selección.
- **Desactivada**: se deja de aplicar el filtro selectivo, pero se conservan las marcas de las carpetas para volver a utilizarlo.

El interruptor solo está disponible si existe al menos una carpeta activa y marcada. Si no queda ninguna carpeta que reúna ambas condiciones, WMM desactiva la rotación selectiva.

Al activarla, WMM activa **Presentación de diapositivas** si estaba apagada y desactiva **Solo favoritos**, porque ambos modos de selección son alternativos. Al desactivar la rotación selectiva no se restaura automáticamente el modo anterior.

#### Rotación

Define cómo se reparten los cambios de fondo entre los monitores. La etiqueta muestra el modo y el tipo de selección utilizado:

- **Síncrono (Sync)**: todos los monitores cambian a la vez. Con **Solo favoritos** se utilizan presets completos.
- **Asíncrono (Async)**: los monitores cambian por turnos de forma independiente. Con **Solo favoritos** se utilizan imágenes individuales de la lista de favoritos.

En las transiciones, el modo síncrono utiliza un fundido a negro y el asíncrono una fusión entre imágenes, según las posibilidades del entorno de escritorio.

### Modo Panorámico

El interruptor activa o desactiva **Spanned**, que utiliza una única imagen extendida por el conjunto de monitores. Solo tiene efecto cuando hay más de un monitor activo.

Esta cabecera también agrupa los ajustes generales de composición, que siguen siendo utilizables aunque **Spanned** esté desactivado.

#### Relación de aspecto

Controla cómo se adapta la imagen al espacio disponible:

- **Escalado (Scaled)**: mantiene las proporciones. El espacio sobrante se rellena con el fondo seleccionado.
- **Zoom**: cubre todo el espacio sin deformar la imagen, recortando las partes que sobresalgan.
- **Estirado (Stretched)**: ajusta la imagen a las dimensiones exactas, aunque pueda deformarse.

#### Efecto de imagen

- **Ninguno (None)**: no aplica efectos.
- **Sepia (Sepia)**: da a la imagen un tono envejecido.
- **Blanco y negro (Black and White)**: convierte la imagen a escala de grises.

#### Efecto de fondo

Define cómo se rellena el espacio que la imagen deja libre, principalmente cuando se utiliza **Escalado**:

- **Difuminado (Blur)**: muestra una copia desenfocada de la imagen.
- **Color**: utiliza el color sólido o degradado configurado en **Color de fondo**.

#### Color de fondo

Se utiliza cuando una imagen no llena la pantalla o cuando un monitor no tiene imagen asignada:

- **Color sólido**: permite elegir un único color.
- **Degradado horizontal**: mezcla dos colores de izquierda a derecha.
- **Degradado vertical**: mezcla dos colores de arriba abajo.

### Presentación de diapositivas

Su interruptor activa o desactiva el temporizador de cambio automático. Los dos valores de esta subsección pueden ajustarse sin necesidad de encenderlo.

#### Frecuencia máxima

Establece, en minutos, el valor máximo que puede seleccionarse para el intervalo de rotación desde el menú de WMM.

#### Diapositivas cada...

Define cuántos minutos transcurren entre cambios automáticos de fondo. Su valor se coordina con el máximo configurado para que el intervalo no lo supere.

### Metadatos de imagen

Permite mostrar información de la imagen sobre el fondo de pantalla generado por WMM. El interruptor de la cabecera activa o desactiva esa información sin modificar los archivos originales.

#### Campos visibles

Pulsa **Seleccionar** para elegir qué datos se mostrarán. El diálogo organiza los campos por categorías, como imagen, autor, origen, fechas y geolocalización. Solo se puede mostrar la información disponible para cada imagen.

- **Aplicar**: confirma la selección y actualiza el resultado sin cerrar el diálogo.
- **Guardar**: confirma la selección y cierra el diálogo.
- **Cancelar**: cierra el diálogo sin guardar los cambios pendientes desde la última aplicación.

#### Fuente y tamaño

Permite elegir la tipografía y el tamaño utilizados para mostrar los metadatos.

#### Posición

Sitúa el bloque de información en una de las cuatro esquinas: superior izquierda, inferior izquierda, superior derecha o inferior derecha.

#### Margen horizontal

Ajusta la separación horizontal del bloque respecto al borde seleccionado, de **0 a 100 píxeles**.

#### Margen vertical

Ajusta la separación vertical del bloque respecto al borde seleccionado, de **0 a 100 píxeles**.

#### Opacidad del fondo

Controla la transparencia del fondo que aparece detrás de los metadatos, de **0 % (transparente)** a **100 % (opaco)**.

Los cambios de aspecto, posición, márgenes y opacidad se reflejan al recomponer el fondo de pantalla.

## Favoritos

Gestiona tus combinaciones de fondos favoritas. Puedes crear, cargar, modificar y eliminar presets. Un *preset* es una composición guardada que puedes recuperar en cualquier momento.

### Switch "Solo favoritos"

Si lo activas, la presentación de diapositivas utiliza exclusivamente tus favoritos.

- En modo **síncrono** se utilizan los presets guardados.
- En modo **asíncrono** se utilizan las imágenes individuales de la lista de favoritos.

### Caja Presets (izquierda)

- **Cargar un preset en los monitores**: haz clic derecho sobre el nombre del preset y selecciona *"Cargar en monitores"*. El preset se cargará en modo de edición para que puedas verlo y modificarlo antes de aplicarlo.
- **Cambiar el nombre de un preset**: haz un clic lento sobre el nombre del preset. Cuando el texto se vuelva editable, escribe el nuevo nombre y pulsa Enter.
- **Eliminar un preset**: haz clic derecho sobre el preset y selecciona *"Eliminar el preset"*. También puedes seleccionarlo y pulsar el botón de la papelera.
- **Eliminar una imagen de un preset**: haz clic derecho sobre la imagen dentro del preset y selecciona *"Eliminar la imagen"*. El monitor conservará su posición en el preset pero quedará sin imagen.
- **Abrir una imagen del preset**: haz doble clic sobre la imagen para abrirla con el visor predeterminado del sistema.

### Caja Favoritos (derecha)

- **Añadir una imagen a favoritos**: desde la galería de miniaturas, haz clic derecho sobre una imagen y selecciona *"Añadir a favoritos"*. También puedes hacerlo desde los gestores de archivos compatibles con WMM.
- **Seleccionar varias imágenes**: utiliza **Ctrl+clic** para una selección discontinua o **Mayús+clic** para seleccionar un rango.
- **Eliminar una imagen de favoritos**: haz clic derecho sobre la imagen y selecciona *"Eliminar de favoritos"*.
- **Abrir una imagen**: haz doble clic para abrirla con el visor de imágenes predeterminado del sistema.

### Botones de eliminación

Tanto la caja de Presets como la de Favoritos tienen un botón con icono de papelera en la parte inferior derecha.

El botón elimina el elemento seleccionado en ese momento. Si hay varias imágenes seleccionadas en la lista de favoritos, las elimina todas de la lista.

## Fuentes de imagen

Desde aquí puedes añadir, eliminar y gestionar las carpetas que WMM utiliza como biblioteca de imágenes.

Si una fuente es recursiva, se muestran también sus subcarpetas y puedes decidir cuáles permanecen activas.

En esta sección **WMM nunca elimina las carpetas ni las imágenes originales del disco**. Las operaciones de limpieza afectan únicamente a la biblioteca interna y a las miniaturas almacenadas en caché.

### Botón "Añadir una fuente"

Abre un diálogo para seleccionar una carpeta del sistema.

- **Incluir subcarpetas (Recursivo)**: actívalo si quieres que WMM incluya también las subcarpetas de esa fuente.
- Si lo dejas desactivado, solo se utilizarán las imágenes situadas directamente en la carpeta raíz.
- Al pulsar **Añadir**, WMM registra la nueva fuente, sincroniza su contenido y actualiza la galería.
- Cuando termina la operación, las imágenes disponibles aparecen en la sección **Miniaturas**.

### Carpeta Online

La entrada **Online** del árbol de fuentes permite vincular un directorio del sistema a las imágenes descargadas mediante la funcionalidad Online.

Para establecer su ubicación, selecciona **Online** en el árbol y pulsa **Añadir una fuente**. Se abrirá el selector de carpetas para elegir el directorio que deseas utilizar.

Si ya existe un directorio vinculado, el mismo procedimiento permite modificar su ubicación.

Esta operación establece o cambia la carpeta utilizada por Online, sin eliminar los archivos originales de la ubicación anterior.

### Botón "Eliminar una fuente"

Elimina la fuente seleccionada de la biblioteca de WMM.

Antes de hacerlo se muestra un diálogo de confirmación. Si aceptas:

- La fuente desaparece de la lista.
- Sus imágenes dejan de estar disponibles para WMM.
- Se retiran de la biblioteca y de la caché los datos asociados a esa fuente.

Los archivos originales permanecen intactos en el disco.

### Botón "Resincronizar"

Revisa las fuentes configuradas y pone la biblioteca al día con el contenido real de las carpetas.

Úsalo cuando:

- hayas añadido, eliminado, movido o renombrado imágenes fuera de WMM;
- hayas modificado imágenes con otro programa;
- hayas cambiado la estructura de las carpetas;
- aparezca el aviso **"Sources need resynchronization"**;
- quieras reconciliar de forma global el estado de todas las fuentes.

Durante la sincronización, WMM detecta las imágenes nuevas, modificadas o eliminadas y actualiza la biblioteca y las miniaturas necesarias.

### Aviso "Sources need resynchronization"

Este aviso indica que la configuración actual de las fuentes y el contenido que WMM tiene preparado para mostrar todavía no coinciden completamente.

No es un error. Puede aparecer, por ejemplo, después de activar o desactivar carpetas, cambiar la opción **Recursivo** o reactivar una carpeta cuya caché ya había sido eliminada.

Pulsa **Resincronizar** para actualizar globalmente la biblioteca.

Si únicamente quieres recuperar una subcarpeta activa que no tiene caché, puedes utilizar **Generar miniaturas** desde su menú contextual.

### Navegación por el árbol de carpetas

#### Seleccionar una carpeta

Al seleccionar una carpeta en el árbol, la sección **Miniaturas** muestra únicamente las imágenes correspondientes a esa carpeta.

Para visualizar nuevamente la totalidad de la biblioteca, selecciona **TODOS**.

#### Doble clic en una carpeta

Abre la carpeta con el gestor de archivos predeterminado del sistema.

#### Clic derecho sobre una carpeta

El menú contextual ofrece las acciones disponibles según el tipo y estado de la carpeta:

- **Activar / Desactivar carpeta**: cambia si sus imágenes forman parte de la biblioteca activa. El cambio de visibilidad es inmediato y no inicia por sí solo una sincronización completa.
- **Activar subcarpetas / Desactivar subcarpetas**: en una fuente recursiva, permite cambiar de una vez el estado de sus subcarpetas.
- **Generar miniaturas**: está disponible para una subcarpeta activa que todavía no tiene contenido preparado en caché. Procesa únicamente esa subcarpeta.
- **Eliminar caché**: aparece para carpetas inactivas. Elimina de WMM la caché asociada a esa carpeta, pero no toca las imágenes originales.
- **Añadir a rotación selectiva / Eliminar de rotación selectiva**: disponible únicamente para carpetas activas. Permite incluir o excluir la carpeta y todas sus subcarpetas de la rotación selectiva. Esta acción no activa ni desactiva el modo, que se controla desde **Opciones**. Las carpetas inactivas no participan en la rotación, aunque conserven su marca.

Si una carpeta se reactiva mientras su caché todavía existe, WMM puede reutilizarla inmediatamente.

Si se reactiva después de haber eliminado su caché, quedará activa pero sus imágenes no aparecerán hasta que utilices **Resincronizar** o **Generar miniaturas**.

### Activar / Desactivar la recursividad

La columna **Recursivo** aparece en las fuentes raíz.

- **Activado**: las subcarpetas forman parte de la fuente.
- **Desactivado**: WMM utiliza únicamente la carpeta raíz.

El cambio se refleja inmediatamente en el árbol y en la visibilidad de las imágenes.

Activar **Recursivo** permite a WMM descubrir las subcarpetas, pero no obliga a reconstruir automáticamente imágenes o miniaturas que ya no estén en caché. En ese caso puedes usar **Resincronizar** para toda la biblioteca o **Generar miniaturas** para una subcarpeta concreta.

## Monitores

Aquí se muestran tus monitores como miniaturas. La sección se actualiza con los cambios de fondo, geometría y estado de las pantallas.

### Botonera de alineación

En la cabecera encontrarás tres botones: `[` , `•` y `]`. Permiten cambiar la alineación horizontal del bloque de monitores dentro de la ventana:

- **`[`**: alineación a la izquierda.
- **`•`**: alineación centrada.
- **`]`**: alineación a la derecha.

Es útil cuando tienes monitores con geometrías muy diferentes y quieres ajustar visualmente la previsualización.

### Modo normal

En modo normal, la sección muestra una miniatura de cada monitor con su imagen asignada y un interruptor para activarlo o desactivarlo.

#### Interruptores de monitor

- **Activado**: el monitor muestra la imagen asignada. Si no tiene ninguna, WMM puede asignarle una según su orientación.
- **Desactivado**: el monitor se rellena con el color de fondo seleccionado y no participa en la rotación de diapositivas.

Si el **Modo Panorámico** está activado, los interruptores quedan bloqueados porque una única imagen se utiliza para la composición completa.

#### Botones de acción

- **Casilla "Favorito"**: si la marcas, al pulsar **Aceptar** se guardará la composición actual como un preset.
- **Aceptar**: aplica los cambios a las pantallas. Si la casilla **Favorito** está marcada, también guarda el preset.
- **Actualizar**: refresca la vista de los monitores desde el motor.

### Modo de edición

Pulsa el botón **Modo de edición** con el icono del lápiz para asignar imágenes manualmente a los monitores.

#### Arrastrar y soltar (Drag & Drop)

Puedes arrastrar cualquier imagen desde la galería de miniaturas y soltarla sobre el monitor virtual al que quieras asignarla.

#### Panel de opciones de edición

Cuando el modo de edición está activo aparecen opciones específicas para la composición:

- **Extender (Spanned)**: activa o desactiva el Modo Panorámico para esta composición.
- **Relación de aspecto**: elige el modo de ajuste de las imágenes.
- **Efectos**: aplica un efecto de imagen a la composición.

Los cambios pueden previsualizarse mientras editas.

Estos valores se guardan junto con el preset y tienen prioridad sobre la configuración global cuando ese preset se utiliza.

#### Botones de acción en modo edición

- **Casilla "Favorito"**: permite guardar la composición editada como preset.
- **Aceptar**: aplica los cambios y sale del modo de edición. Si la casilla está marcada, también guarda el preset.
- **Actualizar**: vacía las imágenes asignadas a los monitores para que puedas reconstruir la composición desde cero.

## Miniaturas

Esta sección muestra las imágenes disponibles en la biblioteca de WMM. Las miniaturas se almacenan en caché para que la navegación sea rápida.

### Botón Actualizar

Recarga la vista de miniaturas y reconstruye las que sean necesarias a partir de la biblioteca que WMM ya tiene sincronizada.

Este botón **no sustituye a Resincronizar**. Si has añadido, eliminado, movido o modificado archivos originales fuera de WMM, utiliza **Resincronizar** para actualizar primero la biblioteca.

### Botones H / V

Los botones **Horizontal** y **Vertical** permiten saltar rápidamente al primer elemento de cada orientación dentro de la galería.

### Botón Favoritos

Muestra una vista específica con las imágenes guardadas como favoritas, incluidas las imágenes que forman parte de tus **Presets**.

### Botón Online

Abre el buscador de fondos de pantalla en Internet. Permite consultar imágenes de servicios externos, descargarlas e incorporarlas a la biblioteca de WMM.

Online dispone de una galería independiente de las miniaturas locales. Las búsquedas no modifican la biblioteca ni las imágenes originales.

#### Uso responsable

Al acceder a Online se presenta el documento **Uso responsable de servicios y recursos de terceros**, que explica los principios de integración, las condiciones de los proveedores y las responsabilidades relacionadas con sus contenidos.

Para continuar, marca **He leído y comprendido este documento** y pulsa **Aceptar**.

La casilla **No volver a mostrar** permite omitir esta pantalla en accesos posteriores, una vez leído y entendido el documento.

Puedes consultar nuevamente su contenido desde **Acerca de WMM > Licencias**.

#### Búsqueda y filtros

El buscador permite combinar tres criterios:

- **Buscar**: introduce palabras o términos relacionados con las imágenes que deseas encontrar en **inglés**. También puedes realizar búsquedas sin introducir texto.
- **Relación de aspecto**: selecciona cualquier proporción, una orientación horizontal o vertical, o una proporción concreta, como 16:9, 21:9, 32:9 o 9:16.
- **Proveedor**: selecciona **Cualquiera** para consultar todos los proveedores disponibles, o elige uno individualmente.

Actualmente WMM integra **Wallhaven** y **Alpha Coders**.

Pulsa **Buscar** o Enter para iniciar la consulta.

El botón de búsqueda vuelve a estar disponible cuando modificas alguno de los criterios. Los filtros se aplican según las posibilidades de cada proveedor.

#### Resultados y navegación

Las imágenes encontradas aparecen progresivamente como miniaturas, indicando su resolución y procedencia.

Cuando se consultan varios proveedores, los resultados se agrupan por servicio. Puedes pulsar sobre el nombre o logotipo del proveedor para visitar su página web.

Cada miniatura dispone de un acceso a su página de origen, que se abre en el navegador predeterminado.

El botón **Cargar más** permite obtener la siguiente página de resultados sin eliminar las páginas anteriores.

Si modificas los criterios de búsqueda, deberás pulsar nuevamente **Buscar** antes de continuar cargando resultados.

#### Carpeta de descargas Online

Las imágenes descargadas se guardan en la carpeta **Online**, cuya ubicación se configura desde **Fuentes de imagen**.

Para establecerla o modificarla, selecciona la entrada **Online** en el árbol de fuentes y utiliza el botón **Añadir una fuente**.

Si no hay una carpeta Online válida configurada, WMM informa de ello y no inicia la descarga.

Desvincular esta carpeta de WMM no elimina sus archivos originales del disco.

#### Selección y descarga

Las miniaturas que permiten descargar su imagen original muestran un botón de selección.

Puedes seleccionar hasta **5 imágenes por lote**. El botón **Descargar** muestra cuántas imágenes has seleccionado y permite iniciar su descarga.

Durante la operación se muestra el progreso de cada archivo. WMM respeta las limitaciones de los proveedores e introduce una pausa preventiva entre descargas consecutivas.

Las imágenes descargadas correctamente se identifican como **Descargadas** y dejan de estar disponibles para una nueva selección, evitando descargas redundantes.

Al finalizar, WMM solicita automáticamente la sincronización de las fuentes para incorporar las nuevas imágenes a la biblioteca y generar sus miniaturas.

Las imágenes incorporadas quedan disponibles para las funciones habituales de WMM.

#### Arrastrar imágenes a los monitores

En **Modo de edición**, puedes arrastrar una miniatura Online directamente sobre un monitor virtual.

WMM prepara la imagen original para previsualizarla en la composición, sin exigir que la descargues previamente mediante el botón **Descargar**.

Al pulsar **Aceptar** en el editor, la imagen se incorpora definitivamente a la carpeta Online y se sincroniza con la biblioteca.

#### Claves API

El botón **Claves API** abre el formulario de gestión de credenciales personales para los proveedores disponibles.

En la parte superior encontrarás un apartado **TIP** desplegable con información sobre el uso de estas claves.

Cada proveedor dispone de un campo informativo y dos acciones alternativas:

- **Examinar**: permite seleccionar un archivo que contenga tu clave API personal.
- **Desvincular**: elimina la asociación con ese archivo, sin modificarlo ni borrarlo.

WMM comprueba la validez del contenido antes de vincularlo. Las claves no se guardan directamente en la configuración: únicamente se conserva la ruta del archivo correspondiente.

El uso de claves personales depende de las características y condiciones de cada proveedor.

### Disposición y orden

Las miniaturas se muestran en un mosaico que se adapta al ancho disponible.

Las imágenes se organizan primero por orientación:

- **Horizontales (H)**: se muestran en primer lugar.
- **Verticales (V)**: se muestran a continuación.

Dentro de cada grupo, las imágenes se ordenan por fecha de incorporación a la biblioteca de WMM, mostrando primero las incorporaciones más recientes.

### Interacción con las miniaturas

Puedes interactuar con cualquier miniatura de varias maneras:

- **Doble clic**: abre la imagen original con el visor predeterminado del sistema.
- **Clic derecho**:
  - *"Añadir a favoritos"*: añade la imagen a la lista de favoritos.
  - *"Eliminar de favoritos"*: la elimina de esa lista cuando ya es favorita.
- **Arrastrar (Drag & Drop)**: en modo de edición, puedes arrastrar una miniatura sobre un monitor virtual para asignarle esa imagen.

### Marco de favorito

Las imágenes incluidas en la lista de favoritos se destacan con un marco cuyo color se adapta al tema visual activo.

# Icono de WMM (panel o bandeja del sistema)

El icono de WMM permite acceder a sus controles y herramientas sin abrir el panel de configuración.

- **Clic izquierdo**: abre el menú principal.
- **Clic central**: solicita el siguiente fondo de pantalla.
- **Clic derecho**: abre el menú contextual.

## Menú principal

Reúne los controles de rotación, favoritos, presentación de diapositivas, modo panorámico y metadatos de imagen, además de la acción para cambiar inmediatamente el fondo.

### Favoritos

El menú **Favoritos** de WMM permite acceder rápidamente a los presets guardados y crear otros nuevos a partir de la composición actual.

#### Switch "Solo favoritos"

Cuando está activado, la presentación de diapositivas utiliza únicamente contenido guardado como favorito:

- **Modo síncrono**: selecciona un preset y aplica la composición completa.
- **Modo asíncrono**: utiliza imágenes individuales de la lista de favoritos.

Si activas **Solo favoritos** mientras la presentación de diapositivas está apagada, WMM la activa automáticamente para que la rotación pueda funcionar.

#### Añadir un preset

Pulsa **"Añadir Preset a favorito"** para guardar la composición actual.

Se abre un diálogo donde puedes indicar el nombre del preset. WMM propone un nombre automático, por ejemplo *"Bookmark 01"*, que puedes sustituir por el que quieras.

- **Nombre en blanco**: WMM avisa y no guarda el preset.
- **Nombre repetido**: debes elegir un nombre diferente.
- **Grabación del preset**: se guarda la configuración actual de los monitores, incluyendo imágenes y opciones asociadas a la composición.

#### Lista de presets

Debajo de los controles aparece la lista de presets guardados.

- **Cargar un preset**: pulsa sobre su nombre para aplicarlo. WMM detiene el temporizador si estaba activo y carga la composición guardada.
- **Eliminar un preset**: pulsa el icono de la papelera y confirma la eliminación.

### Presentación de diapositivas

Desde este menú puedes controlar el cambio automático de fondos sin abrir el panel de control.

#### Switch "Activado / Desactivado"

El interruptor principal enciende o apaga el temporizador de rotación.

- **Activado**: comienza la cuenta atrás para el siguiente cambio.
- **Desactivado**: se mantiene la composición actual hasta que vuelvas a activar la presentación o fuerces una rotación manual.

El estado se sincroniza automáticamente con el panel de control.

#### Intervalo

Permite indicar cuántos minutos deben transcurrir entre cambios.

Según el entorno de escritorio, el control puede mostrarse como deslizador o mediante botones de ajuste. El valor mínimo es de 1 minuto y el máximo viene definido por **Frecuencia máxima** en el panel de control.

Los cambios del intervalo se aplican al temporizador de WMM.

### Monitores (Modo de Rotación)

Controla cómo se reparten los cambios de fondo entre las pantallas.

- **ASYNC (One)**: los monitores cambian por turnos. En cada ciclo solo uno recibe una nueva imagen.
- **SYNC (All)**: todos los monitores cambian a la vez.

El cambio de modo es inmediato y no requiere reiniciar la presentación de diapositivas.

### Modo Panorámico (Spanned)

Activa o desactiva el fondo panorámico.

Cuando está activo, WMM utiliza una única imagen para construir una composición que cubre el conjunto de monitores respetando su posición y geometría.

Esta opción solo tiene efecto cuando hay más de un monitor activo.

Mientras **Spanned** está activado, los interruptores individuales de los monitores quedan bloqueados porque la composición es común a todas las pantallas.

### Metadatos de imagen

Permite mostrar u ocultar la información de la imagen directamente desde el menú principal de WMM, sin necesidad de abrir el panel de control.

- **Activado**: muestra los metadatos según los campos, fuente, posición y demás opciones configuradas.
- **Desactivado**: oculta los metadatos sin perder su configuración.

Los cambios se aplican al fondo de pantalla y se sincronizan con la sección **Metadatos de imagen** del panel de control.

### Siguiente fondo

Solicita un cambio inmediato de fondo de pantalla, utilizando el modo de rotación y la configuración actuales de WMM.

- **Clic izquierdo**: solicita el siguiente fondo sin necesidad de esperar al temporizador.
- **Clic derecho**: abre el formulario para configurar el atajo de teclado.

Si existe una combinación de teclas asignada, se muestra a la derecha de "Siguiente fondo".

#### Atajos de teclado

WMM permite asignar un atajo global para solicitar el siguiente fondo de pantalla sin abrir su menú principal.

Para configurarlo, haz clic derecho sobre "Siguiente fondo". Se abrirá un formulario que muestra la combinación actualmente registrada y permite modificarla.

- **Asignar o cambiar**: pulsa la combinación deseada en el campo de captura. No es necesario escribirla manualmente.
- **Borrar**: limpia el campo de captura para retirar el atajo actual o introducir uno nuevo.
- **Aceptar**: valida y registra la combinación seleccionada. Si el campo está vacío, elimina el atajo registrado.
- **Cancelar**: descarta los cambios y conserva la combinación anterior.

El formulario informa cuando una combinación no está admitida, está incompleta o se detecta que ya está en uso. En estos casos, deberás seleccionar otra combinación.

Durante la configuración, el atajo anterior se suspende temporalmente para permitir su modificación. Si cancelas la operación, WMM lo restaura automáticamente.

Los cambios confirmados se conservan entre sesiones y la combinación registrada se muestra junto a "Siguiente fondo" en el menú principal.

## Menú contextual

El menú contextual reúne las herramientas de configuración, mantenimiento e información de WMM:

- **Ajustes**: abre el panel de control.
- **Sincronizar biblioteca**: revisa todas las fuentes y actualiza la biblioteca.
- **Gestor de instalación**: disponible en Linux y Windows Open Code. Permite realizar las operaciones de mantenimiento de WMM. La versión compilada de Windows utiliza Inno Setup.
- **Visor de registro de depuración**: abre el visor de actividad y diagnóstico.
- **Ayuda**: abre este manual.
- **Iniciar WMM con Windows** (solo Windows): activa o desactiva el inicio automático de WMM al iniciar sesión.
- **Acerca de WMM Manager**: muestra información sobre la aplicación.
- **Salir de WMM**: cierra WMM.

### Sincronizar biblioteca

Revisa todas las fuentes configuradas y actualiza la biblioteca de WMM para que coincida con el contenido actual del disco.

La sincronización detecta imágenes nuevas, modificadas y eliminadas, actualiza las referencias necesarias y reconstruye las miniaturas que correspondan.

Es especialmente útil después de realizar cambios en las carpetas desde fuera de WMM o cuando aparece el aviso **"Resincronizar fuentes"**.

La sincronización no modifica ni elimina las imágenes originales.

### Gestor de instalación

WMM dispone de diferentes mecanismos de mantenimiento según el sistema operativo y el tipo de instalación.

#### Linux

El Gestor de instalación permite actualizar, reinstalar o desinstalar WMM mediante una interfaz gráfica.

La ventana muestra la versión instalada y el entorno de escritorio detectado.

- **Actualizar**: comprueba si existe una versión más reciente publicada en GitHub y permite descargarla e instalarla.
- **Reinstalar**: reinstala la versión actual utilizando una copia limpia del paquete de reparación preparado durante la instalación.
- **Desinstalar**: elimina WMM, sus integraciones con el escritorio, configuración y datos asociados.

Las operaciones se ejecutan mediante los scripts de instalación y desinstalación de WMM.

El gestor incorpora un terminal donde puedes consultar el progreso y los mensajes de la operación. Si se requieren permisos administrativos, introduce la contraseña directamente en ese terminal.

Durante una operación de mantenimiento, los demás controles permanecen bloqueados hasta que finaliza el proceso.

#### Windows Open Code

La distribución Open Code dispone de un gestor de mantenimiento propio, desarrollado en PowerShell y accesible desde el menú contextual de WMM.

La ventana muestra la versión instalada, la versión del paquete local y la última versión disponible en GitHub, cuando puede consultarse.

Las operaciones disponibles dependen de las versiones detectadas y de los paquetes disponibles:

- **Instalar**: instala WMM desde una distribución local válida cuando todavía no está instalado.
- **Actualizar**: instala una versión más reciente, procedente del paquete local o de GitHub.
- **Reinstalar**: recupera la versión instalada utilizando el paquete local correspondiente o la copia de reparación de WMM.
- **Volver a una versión anterior**: permite instalar una versión más antigua cuando se dispone de su distribución local.
- **Desinstalar**: elimina WMM, sus integraciones con Windows, configuración y caché.

El gestor solicita confirmación antes de iniciar cada operación e identifica la versión y procedencia del paquete seleccionado.

Si únicamente falta el runtime de una distribución local válida, WMM puede ofrecer su descarga desde GitHub, previa autorización del usuario.

Las operaciones muestran su progreso en una ventana independiente. Los archivos originales de fondos de pantalla no se eliminan durante la desinstalación.

#### Windows — Inno Setup

La distribución compilada de Windows utiliza el instalador Inno Setup y no incluye el Gestor de instalación de Open Code.

- **Instalar**: ejecuta el instalador de WMM y sigue las indicaciones del asistente.
- **Actualizar o reinstalar**: ejecuta el instalador correspondiente a la versión que deseas instalar. Inno Setup gestiona la sustitución de los archivos de la aplicación.
- **Desinstalar**: utiliza la opción de desinstalación de WMM desde Windows o el acceso correspondiente del menú Inicio.

El desinstalador de Inno Setup permite elegir, mediante dos casillas independientes, si deseas eliminar:

- **Caché de miniaturas**: los archivos temporales generados para visualizar las imágenes.
- **Datos de configuración de WMM**: información persistente como preferencias, fuentes, favoritos, perfiles e historial.

Estas opciones aparecen antes de iniciar la desinstalación y permiten decidir qué datos adicionales retirar. Algunos archivos auxiliares de configuración se eliminan como parte de la limpieza habitual.

La desinstalación nunca elimina las imágenes originales del usuario.

### Visor de registro de depuración

El visor de logs muestra en tiempo real la actividad de WMM y resulta útil para consultar lo que está haciendo el motor, el panel o las integraciones de escritorio.

#### Filtros

Puedes filtrar las entradas por **Origen**, **Nivel** y **Motivo**, además de utilizar la búsqueda de texto.

#### Auto-scroll

Mantiene la vista siguiendo automáticamente las nuevas entradas del registro.

#### Orden inverso

Permite mostrar primero las entradas más recientes o mantener el orden cronológico normal.

#### Limpiar registro

El botón de limpieza vacía el registro después de pedir confirmación.

El visor recuerda las preferencias de **Auto-scroll**, **Orden inverso** y el tamaño de su ventana.

### Ayuda

Abre esta ventana de ayuda de WMM.

El índice de navegación aparece a la izquierda y el contenido Markdown formateado a la derecha para que puedas saltar directamente a la sección que necesites.

### Acerca de WMM Manager

Muestra información básica sobre WMM, incluida la versión instalada, nombre de la aplicación y licencia.
En algunos entornos de escritorio también ofrece enlaces de utilidad.

# Gestores de archivos

WMM se integra con **Nemo**, **Nautilus**, **Dolphin**, **Caja**, **Thunar** y **Explorer** cuando estos gestores están disponibles en el sistema.

Al hacer clic derecho sobre una imagen puedes encontrar acciones de WMM para:

- **Añadir a favoritos**.
- **Enviar a un monitor**.
- **Distribuir la imagen en todas las pantallas**.

Según el gestor de archivos, estas acciones pueden aparecer agrupadas dentro de **WMM Manager** o como acciones individuales.

En MATE, la integración con Caja también puede ofrecer una acción para distribuir la imagen actual desde el menú contextual del escritorio.

# Atajos de teclado

WMM registra la acción **Siguiente fondo** en los mecanismos de atajos de **Cinnamon**, **GNOME Shell**, **KDE Plasma 6**, **MATE** y **XFCE**.

Puedes configurar la combinación de teclas desde las herramientas de atajos de tu entorno de escritorio.

Desde WMM 2.0, también puedes asignar, modificar o eliminar el atajo directamente desde el menú principal del icono de WMM. Haz clic derecho sobre **Siguiente fondo** para abrir el formulario de configuración.

A continuación se explica cómo gestionar el atajo desde cada entorno de escritorio Linux.

## En Cinnamon

1. Abre **Configuración del sistema → Teclado → Atajos de teclado**.
2. Entra en **Atajos personalizados**.
3. Busca **"WMM - Siguiente fondo"**.
4. Asigna la combinación que prefieras, por ejemplo `Ctrl+Alt+N`.

## En GNOME Shell

1. Abre la configuración de **Teclado** y sus atajos personalizados.
2. Busca la acción de WMM para **Siguiente fondo**.
3. Asigna la combinación que prefieras.

## En KDE Plasma 6

1. Abre **Configuración del sistema → Atajos**.
2. Busca **WMM Manager** y **Siguiente fondo**.
3. Asigna la combinación de teclas que quieras utilizar.

## En MATE

1. Abre la configuración de **Atajos de teclado** de MATE.
2. Busca **"WMM - Siguiente fondo"**.
3. Asigna la combinación que prefieras.

## En XFCE

1. Abre **Configuración → Teclado → Atajos de aplicación**.
2. Localiza el comando **wmm-next.sh**, registrado por WMM.
3. Selecciona la entrada y edita su atajo.
4. Asigna la combinación de teclas que prefieras.

El atajo solicita una rotación manual utilizando el modo y la configuración actuales de WMM.
