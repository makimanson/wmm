<!--
SPDX-FileCopyrightText: 2026 makimanson
SPDX-License-Identifier: GPL-3.0-or-later

WMM - Wallpaper Multi-Monitor Manager

HELP_es.md -- Archivo de ayuda en castellano

WMM-Title: Ayuda
WMM-Contents: Contenidos
-->

# Entornos de escritorio

WMM dispone actualmente de integración completa con **Cinnamon**, **GNOME Shell**, **KDE Plasma 6** y **MATE**.

El panel de control y las funciones principales son comunes a todos los entornos. Algunos controles pueden cambiar ligeramente de aspecto o ubicación según el escritorio, pero comparten la misma configuración.

# Ajustes

Abre el menú de WMM desde su applet, extensión o plasmoide y selecciona **Ajustes** para abrir el panel de control.

## Opciones

Aquí encontrarás las opciones generales de WMM. Puedes cambiar el comportamiento al iniciar, el modo de aspecto, los efectos de imagen, el fondo y la presentación de diapositivas. Los cambios se reflejan en los monitores virtuales de la sección **Monitores**.

### Icono Ayuda

Abre esta ayuda en una ventana independiente.

### Icono Visor de Logs

Abre el visor de logs de depuración en una ventana aparte. Muestra en tiempo real la actividad de WMM y permite filtrar el registro.

### Icono Reiniciar

Reinicia completamente el motor y el panel de control. Es útil si necesitas volver a cargar WMM durante la sesión.

### Icono Plegar / Expandir

Pliega la columna lateral del panel para dejar más espacio a las secciones de monitores y miniaturas. Al volver a pulsarlo se recupera la vista completa.

WMM recuerda el estado plegado o desplegado del panel.

### Plegar / desplegar secciones

Las distintas secciones del panel de control pueden **plegarse o desplegarse** pulsando sobre su cabecera.

* **Desplegada**: muestra todos los controles y opciones de la sección.
* **Plegada**: oculta su contenido y deja visible únicamente la cabecera.

Esto permite reducir el espacio ocupado por las secciones que no estés utilizando y centrar la vista en las opciones que necesites en cada momento.

El plegado solo afecta a la visualización del panel: **no activa, desactiva ni modifica ninguna opción de WMM**.

### Cambiar el fondo de pantalla al iniciar

Si está **activada**, al iniciar WMM el motor elige imágenes nuevas y genera una nueva composición.

Si está **desactivada**, se conserva la última composición guardada.

### Modo Panorámico

Activa o desactiva el **Modo Panorámico** (*Spanned*). Al activarse, se utiliza una única imagen panorámica que se extiende por todos los monitores a la vez.

Solo está disponible si hay más de un monitor activo.

### Relación de aspecto

Controla cómo se ajusta la imagen dentro de cada monitor:

- **Escalado** (*Scaled*): la imagen se reduce o amplía sin deformarla. Si no llena todo el monitor, el espacio sobrante se rellena con el color o efecto de fondo seleccionado.
- **Zoom**: la imagen se escala para cubrir todo el monitor. Si la imagen y el monitor tienen proporciones diferentes, las partes sobrantes se recortan.
- **Estirado** (*Stretched*): la imagen se ajusta exactamente al tamaño del monitor, aunque pueda deformarse.

### Efecto de imagen

Aplica un efecto visual sobre la imagen de cada monitor:

- **Ninguno** (*None*): sin efecto.
- **Sepia** (*Sepia*): aplica un tono envejecido a la imagen.
- **Blanco y negro** (*Black and White*): convierte la imagen a escala de grises.

### Efecto de fondo

Rellena el espacio sobrante cuando la imagen no cubre completamente el monitor. Es visible principalmente en modo **Escalado**.

- **Difuminado** (*Blur*): utiliza una copia desenfocada de la propia imagen como fondo.
- **Color**: utiliza el color sólido o degradado seleccionado en **Color de fondo**.

### Color de fondo

Define el fondo utilizado cuando una imagen no ocupa toda la pantalla o cuando un monitor no tiene una imagen asignada.

- **Color sólido** (*Solid color*): un único color plano.
- **Degradado Horizontal** (*Gradient H*): degradado de dos colores de izquierda a derecha.
- **Degradado Vertical** (*Gradient V*): degradado de dos colores de arriba abajo.

### Presentación de diapositivas

Activa o desactiva el cambio automático de imágenes. Cuando está activado, el motor cambia los fondos según la frecuencia y el modo configurados.

### Frecuencia máxima

Establece el límite máximo, en minutos, que puede tener el intervalo de rotación utilizado desde el menú de WMM.

### Diapositivas cada...

Define cada cuántos minutos se realizará un cambio automático de fondo de pantalla.

### Modo de presentación

Controla cómo cambian las imágenes y el efecto de transición durante la presentación de diapositivas:

- **Síncrono** (*Sync*):
    - Aplica un efecto de fundido a negro (Fade-out > Fade-in).
    - Todos los monitores cambian a la vez.
    - Si está activada la opción **Solo favoritos**: la rotación utiliza los presets guardados.

- **Asíncrono** (*Async*):
    - Aplica un efecto de fusión entre imágenes (Crossfade).
    - Los monitores cambian por turnos de manera independiente.
    - Si está activada la opción **Solo favoritos**: la rotación utiliza imágenes individuales de la lista de favoritos.

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

#### Doble clic en una carpeta

Abre la carpeta con el gestor de archivos predeterminado del sistema.

#### Clic derecho sobre una carpeta

El menú contextual ofrece las acciones disponibles según el tipo y estado de la carpeta:

- **Activar / Desactivar carpeta**: cambia si sus imágenes forman parte de la biblioteca activa. El cambio de visibilidad es inmediato y no inicia por sí solo una sincronización completa.
- **Activar subcarpetas / Desactivar subcarpetas**: en una fuente recursiva, permite cambiar de una vez el estado de sus subcarpetas.
- **Generar miniaturas**: está disponible para una subcarpeta activa que todavía no tiene contenido preparado en caché. Procesa únicamente esa subcarpeta.
- **Eliminar caché**: aparece para carpetas inactivas. Elimina de WMM la caché asociada a esa carpeta, pero no toca las imágenes originales.

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
- **Desactivado**: el monitor se rellena con el fondo seleccionado y no participa en la rotación de diapositivas.

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

### Disposición y orden

Las miniaturas se muestran en un mosaico que se adapta al ancho disponible.

El orden es:

- Primero las imágenes **horizontales**, con las incorporadas más recientemente a la biblioteca en primer lugar.
- Después las imágenes **verticales**, también con las incorporadas más recientemente en primer lugar.

### Interacción con las miniaturas

Puedes interactuar con cualquier miniatura de varias maneras:

- **Doble clic**: abre la imagen original con el visor predeterminado del sistema.
- **Clic derecho**:
  - *"Añadir a favoritos"*: añade la imagen a la lista de favoritos.
  - *"Eliminar de favoritos"*: la elimina de esa lista cuando ya es favorita.
- **Arrastrar (Drag & Drop)**: en modo de edición, puedes arrastrar una miniatura sobre un monitor virtual para asignarle esa imagen.

### Marco de favorito

Las imágenes incluidas en la lista de favoritos se destacan con un marco de color verde.

# Favoritos

El menú **Favoritos** de WMM permite acceder rápidamente a los presets guardados y crear otros nuevos a partir de la composición actual.

### Switch "Solo favoritos"

Cuando está activado, la presentación de diapositivas utiliza únicamente contenido guardado como favorito:

- **Modo síncrono**: selecciona un preset y aplica la composición completa.
- **Modo asíncrono**: utiliza imágenes individuales de la lista de favoritos.

Si activas **Solo favoritos** mientras la presentación de diapositivas está apagada, WMM la activa automáticamente para que la rotación pueda funcionar.

### Añadir un preset

Pulsa **"Añadir Preset a favorito"** para guardar la composición actual.

Se abre un diálogo donde puedes indicar el nombre del preset. WMM propone un nombre automático, por ejemplo *"Bookmark 01"*, que puedes sustituir por el que quieras.

- **Nombre en blanco**: WMM avisa y no guarda el preset.
- **Nombre repetido**: debes elegir un nombre diferente.
- **Grabación del preset**: se guarda la configuración actual de los monitores, incluyendo imágenes y opciones asociadas a la composición.

### Lista de presets

Debajo de los controles aparece la lista de presets guardados.

- **Cargar un preset**: pulsa sobre su nombre para aplicarlo. WMM detiene el temporizador si estaba activo y carga la composición guardada.
- **Eliminar un preset**: pulsa el icono de la papelera y confirma la eliminación.

# Presentación de diapositivas

Desde este menú puedes controlar el cambio automático de fondos sin abrir el panel de control.

### Switch "Activado / Desactivado"

El interruptor principal enciende o apaga el temporizador de rotación.

- **Activado**: comienza la cuenta atrás para el siguiente cambio.
- **Desactivado**: se mantiene la composición actual hasta que vuelvas a activar la presentación o fuerces una rotación manual.

El estado se sincroniza automáticamente con el panel de control.

### Intervalo

Permite indicar cuántos minutos deben transcurrir entre cambios.

Según el entorno de escritorio, el control puede mostrarse como deslizador o mediante botones de ajuste. El valor mínimo es de 1 minuto y el máximo viene definido por **Frecuencia máxima** en el panel de control.

Los cambios del intervalo se aplican al temporizador de WMM.

# Monitores (Modo de Rotación)

Controla cómo se reparten los cambios de fondo entre las pantallas.

- **ASYNC (One)**: los monitores cambian por turnos. En cada ciclo solo uno recibe una nueva imagen.
- **SYNC (All)**: todos los monitores cambian a la vez.

El cambio de modo es inmediato y no requiere reiniciar la presentación de diapositivas.

# Modo Panorámico (Spanned)

Activa o desactiva el fondo panorámico.

Cuando está activo, WMM utiliza una única imagen para construir una composición que cubre el conjunto de monitores respetando su posición y geometría.

Esta opción solo tiene efecto cuando hay más de un monitor activo.

Mientras **Spanned** está activado, los interruptores individuales de los monitores quedan bloqueados porque la composición es común a todas las pantallas.

# Herramientas

El menú **Herramientas** reúne los accesos operativos comunes de WMM:

- **Ajustes**: abre el panel de control.
- **Sincronizar biblioteca**: revisa todas las fuentes y actualiza la biblioteca.
- **Gestor de instalación**: permite actualizar, reinstalar o desinstalar WMM.
- **Visor de registro de depuración**: abre el visor de actividad y diagnóstico.
- **Ayuda**: abre este manual.

## Sincronizar Biblioteca

Revisa todas las fuentes configuradas y actualiza la biblioteca de WMM para que coincida con el contenido actual del disco.

La sincronización detecta imágenes nuevas, modificadas y eliminadas, actualiza las referencias necesarias y reconstruye las miniaturas que correspondan.

Es especialmente útil después de realizar cambios en las carpetas desde fuera de WMM o cuando aparece el aviso **"Resincronizar fuentes"**.

La sincronización no modifica ni elimina las imágenes originales.

## Gestor de instalación

**El Gestor de instalación** permite realizar las tareas de mantenimiento de WMM desde una interfaz gráfica.

La ventana muestra la versión instalada y el entorno de escritorio detectado.

### Actualizar

Si existe una versión más reciente, permite descargarla, validarla e iniciar la actualización.

### Reinstalar

Reinstala la versión actual para reparar o recuperar una instalación dañada conservando los datos de usuario que corresponda.

### Desinstalar

Inicia el desinstalador de WMM y elimina la aplicación y sus integraciones de escritorio.

Antes de las operaciones que lo necesiten, el terminal integrado puede solicitar la contraseña administrativa. Escribe la contraseña directamente en ese terminal.

Durante una operación de mantenimiento los demás controles permanecen bloqueados hasta que finaliza el proceso.

## Visor de registro de depuración

El visor de logs muestra en tiempo real la actividad de WMM y resulta útil para consultar lo que está haciendo el motor, el panel o las integraciones de escritorio.

### Filtros

Puedes filtrar las entradas por **Origen**, **Nivel** y **Motivo**, además de utilizar la búsqueda de texto.

### Auto-scroll

Mantiene la vista siguiendo automáticamente las nuevas entradas del registro.

### Orden inverso

Permite mostrar primero las entradas más recientes o mantener el orden cronológico normal.

### Limpiar registro

El botón de limpieza vacía el registro después de pedir confirmación.

El visor recuerda las preferencias de **Auto-scroll**, **Orden inverso** y el tamaño de su ventana.

## Ayuda

Abre la ventana de ayuda de WMM.

El índice de navegación aparece a la izquierda y el contenido Markdown formateado a la derecha para que puedas saltar directamente a la sección que necesites.

# Acerca de WMM Manager

Muestra información básica sobre WMM, incluida la versión instalada, nombre de la aplicación y licencia.
En algunos entornos de escritorio también ofrece enlaces de utilidad.

# Gestores de archivos

WMM se integra con **Nemo**, **Nautilus**, **Dolphin** y **Caja** cuando estos gestores están disponibles en el sistema.

Al hacer clic derecho sobre una imagen puedes encontrar acciones de WMM para:

- **Añadir a favoritos**.
- **Enviar a un monitor**.
- **Distribuir la imagen en todas las pantallas**.

Según el gestor de archivos, estas acciones pueden aparecer agrupadas dentro de **WMM Manager** o como acciones individuales.

En MATE, la integración con Caja también puede ofrecer una acción para distribuir la imagen actual desde el menú contextual del escritorio.

# Atajos de teclado

WMM registra la acción **Siguiente fondo** en los mecanismos de atajos de **Cinnamon**, **GNOME Shell**, **KDE Plasma 6** y **MATE**.

La combinación de teclas la eliges tú desde la configuración de atajos de tu escritorio.

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

El atajo solicita una rotación manual utilizando el modo y la configuración actuales de WMM.
