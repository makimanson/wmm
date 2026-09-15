<!--
SPDX-FileCopyrightText: 2026 makimanson
SPDX-License-Identifier: GPL-3.0-or-later

WMM - Wallpaper Multi-Monitor Manager

HELP_ca.md -- Fitxer d'ajuda en català

WMM-Title: Ajuda
WMM-Contents: Continguts
-->

# Entorns d'escriptori

WMM disposa actualment d'integració completa amb **Cinnamon**, **GNOME Shell**, **KDE Plasma 6** i **MATE**.

El tauler de control i les funcions principals són comunes a tots els entorns. Alguns controls poden canviar lleugerament d'aspecte o d'ubicació segons l'escriptori, però comparteixen la mateixa configuració.

# Ajustaments

Obre el menú de WMM des del seu applet, extensió o plasmoide i selecciona **Ajustaments** per obrir el tauler de control.

## Opcions

Aquí trobaràs les opcions generals de WMM. Pots canviar el comportament en iniciar, el mode d'aspecte, els efectes d'imatge, el fons i la presentació de diapositives. Els canvis es reflecteixen als monitors virtuals de la secció **Monitors**.

### Icona Ajuda

Obre aquesta ajuda en una finestra independent.

### Icona Visor de Logs

Obre el visor de logs de depuració en una finestra a part. Mostra en temps real l'activitat de WMM i permet filtrar el registre.

### Icona Reiniciar

Reinicia completament el motor i el tauler de control. És útil si necessites tornar a carregar WMM durant la sessió.

### Icona Plegar / Desplegar

Plega la columna lateral del tauler per deixar més espai a les seccions de monitors i miniatures. En tornar a prémer-la es recupera la vista completa.

WMM recorda l'estat plegat o desplegat del tauler.

### Plegar / desplegar seccions

Les diferents seccions del tauler de control es poden **plegar o desplegar** prement sobre la capçalera.

* **Desplegada**: mostra tots els controls i opcions de la secció.
* **Plegada**: n'amaga el contingut i deixa visible únicament la capçalera.

Això permet reduir l'espai ocupat per les seccions que no estiguis utilitzant i centrar la vista en les opcions que necessitis en cada moment.

El plegat només afecta la visualització del tauler: **no activa, desactiva ni modifica cap opció de WMM**.

### Canviar el fons de pantalla en iniciar

Si està **activada**, en iniciar WMM el motor tria imatges noves i genera una composició nova.

Si està **desactivada**, es conserva l'última composició desada.

### Mode Panoràmic

Activa o desactiva el **Mode Panoràmic** (*Spanned*). En activar-lo, s'utilitza una única imatge panoràmica que s'estén per tots els monitors alhora.

Només està disponible si hi ha més d'un monitor actiu.

### Relació d'aspecte

Controla com s'ajusta la imatge dins de cada monitor:

- **Escalat** (*Scaled*): la imatge es redueix o s'amplia sense deformar-la. Si no omple tot el monitor, l'espai sobrant s'omple amb el color o efecte de fons seleccionat.
- **Zoom**: la imatge s'escala per cobrir tot el monitor. Si la imatge i el monitor tenen proporcions diferents, les parts sobrants es retallen.
- **Estirat** (*Stretched*): la imatge s'ajusta exactament a la mida del monitor, encara que es pugui deformar.

### Efecte d'imatge

Aplica un efecte visual sobre la imatge de cada monitor:

- **Cap** (*None*): sense efecte.
- **Sèpia** (*Sepia*): aplica un to envellit a la imatge.
- **Blanc i negre** (*Black and White*): converteix la imatge a escala de grisos.

### Efecte de fons

Omple l'espai sobrant quan la imatge no cobreix completament el monitor. És visible principalment en mode **Escalat**.

- **Difuminat** (*Blur*): utilitza una còpia desenfocada de la mateixa imatge com a fons.
- **Color**: utilitza el color sòlid o degradat seleccionat a **Color de fons**.

### Color de fons

Defineix el fons utilitzat quan una imatge no ocupa tota la pantalla o quan un monitor no té cap imatge assignada.

- **Color sòlid** (*Solid color*): un únic color pla.
- **Degradat horitzontal** (*Gradient H*): degradat de dos colors d'esquerra a dreta.
- **Degradat vertical** (*Gradient V*): degradat de dos colors de dalt a baix.

### Presentació de diapositives

Activa o desactiva el canvi automàtic d'imatges. Quan està activat, el motor canvia els fons segons la freqüència i el mode configurats.

### Freqüència màxima

Estableix el límit màxim, en minuts, que pot tenir l'interval de rotació utilitzat des del menú de WMM.

### Diapositives cada...

Defineix cada quants minuts es farà un canvi automàtic de fons de pantalla.

### Mode de presentació

Controla com canvien les imatges i l'efecte de transició durant la presentació de diapositives:

- **Síncron** (*Sync*):
    - Aplica un efecte de fos a negre (Fade-out > Fade-in).
    - Tots els monitors canvien alhora.
    - Si està activada l'opció **Només preferits**: la rotació utilitza els presets desats.

- **Asíncron** (*Async*):
    - Aplica un efecte de fusió entre imatges (Crossfade).
    - Els monitors canvien per torns de manera independent.
    - Si està activada l'opció **Només preferits**: la rotació utilitza imatges individuals de la llista de preferits.

## Preferits

Gestiona les teves combinacions de fons preferides. Pots crear, carregar, modificar i eliminar presets. Un *preset* és una composició desada que pots recuperar en qualsevol moment.

### Switch "Només preferits"

Si l'actives, la presentació de diapositives utilitza exclusivament els teus preferits.

- En mode **síncron** s'utilitzen els presets desats.
- En mode **asíncron** s'utilitzen les imatges individuals de la llista de preferits.

### Caixa Presets (esquerra)

- **Carregar un preset als monitors**: fes clic dret sobre el nom del preset i selecciona *"Carrega als monitors"*. El preset es carregarà en mode d'edició perquè el puguis veure i modificar abans d'aplicar-lo.
- **Canviar el nom d'un preset**: fes un clic lent sobre el nom del preset. Quan el text es torni editable, escriu el nom nou i prem Enter.
- **Eliminar un preset**: fes clic dret sobre el preset i selecciona *"Elimina el preset"*. També el pots seleccionar i prémer el botó de la paperera.
- **Eliminar una imatge d'un preset**: fes clic dret sobre la imatge dins del preset i selecciona *"Elimina la imatge"*. El monitor conservarà la seva posició al preset però quedarà sense imatge.
- **Obrir una imatge del preset**: fes doble clic sobre la imatge per obrir-la amb el visor predeterminat del sistema.

### Caixa Preferits (dreta)

- **Afegir una imatge a preferits**: des de la galeria de miniatures, fes clic dret sobre una imatge i selecciona *"Afegeix a preferits"*. També ho pots fer des dels gestors de fitxers compatibles amb WMM.
- **Seleccionar diverses imatges**: utilitza **Ctrl+clic** per a una selecció discontínua o **Majús+clic** per seleccionar un rang.
- **Eliminar una imatge de preferits**: fes clic dret sobre la imatge i selecciona *"Elimina de preferits"*.
- **Obrir una imatge**: fes doble clic per obrir-la amb el visor d'imatges predeterminat del sistema.

### Botons d'eliminació

Tant la caixa de Presets com la de Preferits tenen un botó amb icona de paperera a la part inferior dreta.

El botó elimina l'element seleccionat en aquell moment. Si hi ha diverses imatges seleccionades a la llista de preferits, les elimina totes de la llista.

## Fonts d'imatges

Des d'aquí pots afegir, eliminar i gestionar les carpetes que WMM utilitza com a biblioteca d'imatges.

Si una font és recursiva, també se'n mostren les subcarpetes i pots decidir quines continuen actives.

En aquesta secció **WMM no elimina mai les carpetes ni les imatges originals del disc**. Les operacions de neteja només afecten la biblioteca interna i les miniatures emmagatzemades a la memòria cau.

### Botó "Afegir una font"

Obre un diàleg per seleccionar una carpeta del sistema.

- **Incloure subcarpetes (Recursiu)**: activa-ho si vols que WMM inclogui també les subcarpetes d'aquesta font.
- Si ho deixes desactivat, només s'utilitzaran les imatges situades directament a la carpeta arrel.
- En prémer **Afegir**, WMM registra la font nova, sincronitza el contingut i actualitza la galeria.
- Quan acaba l'operació, les imatges disponibles apareixen a la secció **Miniatures**.

### Botó "Eliminar una font"

Elimina la font seleccionada de la biblioteca de WMM.

Abans es mostra un diàleg de confirmació. Si ho acceptes:

- La font desapareix de la llista.
- Les seves imatges deixen d'estar disponibles per a WMM.
- S'eliminen de la biblioteca i de la memòria cau les dades associades a aquella font.

Els fitxers originals es mantenen intactes al disc.

### Botó "Resincronitzar"

Revisa les fonts configurades i posa la biblioteca al dia amb el contingut real de les carpetes.

Utilitza'l quan:

- hagis afegit, eliminat, mogut o canviat de nom imatges fora de WMM;
- hagis modificat imatges amb un altre programa;
- hagis canviat l'estructura de les carpetes;
- aparegui l'avís **"Sources need resynchronization"**;
- vulguis reconciliar globalment l'estat de totes les fonts.

Durant la sincronització, WMM detecta les imatges noves, modificades o eliminades i actualitza la biblioteca i les miniatures necessàries.

### Avís "Sources need resynchronization"

Aquest avís indica que la configuració actual de les fonts i el contingut que WMM té preparat per mostrar encara no coincideixen completament.

No és un error. Pot aparèixer, per exemple, després d'activar o desactivar carpetes, canviar l'opció **Recursiu** o reactivar una carpeta de la qual ja s'havia eliminat la memòria cau.

Prem **Resincronitzar** per actualitzar globalment la biblioteca.

Si només vols recuperar una subcarpeta activa que no té memòria cau, pots utilitzar **Generar miniatures** des del menú contextual.

### Navegació per l'arbre de carpetes

#### Doble clic en una carpeta

Obre la carpeta amb el gestor de fitxers predeterminat del sistema.

#### Clic dret sobre una carpeta

El menú contextual ofereix les accions disponibles segons el tipus i l'estat de la carpeta:

- **Activar / Desactivar carpeta**: canvia si les seves imatges formen part de la biblioteca activa. El canvi de visibilitat és immediat i no inicia per si sol una sincronització completa.
- **Activar subcarpetes / Desactivar subcarpetes**: en una font recursiva, permet canviar d'una vegada l'estat de les seves subcarpetes.
- **Generar miniatures**: està disponible per a una subcarpeta activa que encara no té contingut preparat a la memòria cau. Processa únicament aquella subcarpeta.
- **Eliminar memòria cau**: apareix per a carpetes inactives. Elimina de WMM la memòria cau associada a aquella carpeta, però no toca les imatges originals.

Si una carpeta es reactiva mentre la seva memòria cau encara existeix, WMM la pot reutilitzar immediatament.

Si es reactiva després d'haver eliminat la memòria cau, quedarà activa però les seves imatges no apareixeran fins que utilitzis **Resincronitzar** o **Generar miniatures**.

### Activar / Desactivar la recursivitat

La columna **Recursiu** apareix a les fonts arrel.

- **Activat**: les subcarpetes formen part de la font.
- **Desactivat**: WMM utilitza únicament la carpeta arrel.

El canvi es reflecteix immediatament a l'arbre i en la visibilitat de les imatges.

Activar **Recursiu** permet que WMM descobreixi les subcarpetes, però no obliga a reconstruir automàticament imatges o miniatures que ja no siguin a la memòria cau. En aquest cas pots utilitzar **Resincronitzar** per a tota la biblioteca o **Generar miniatures** per a una subcarpeta concreta.

## Monitors

Aquí es mostren els monitors com a miniatures. La secció s'actualitza amb els canvis de fons, geometria i estat de les pantalles.

### Botonera d'alineació

A la capçalera trobaràs tres botons: `[` , `•` i `]`. Permeten canviar l'alineació horitzontal del bloc de monitors dins de la finestra:

- **`[`**: alineació a l'esquerra.
- **`•`**: alineació centrada.
- **`]`**: alineació a la dreta.

És útil quan tens monitors amb geometries molt diferents i vols ajustar visualment la previsualització.

### Mode normal

En mode normal, la secció mostra una miniatura de cada monitor amb la imatge assignada i un interruptor per activar-lo o desactivar-lo.

#### Interruptors de monitor

- **Activat**: el monitor mostra la imatge assignada. Si no en té cap, WMM en pot assignar una segons l'orientació.
- **Desactivat**: el monitor s'omple amb el fons seleccionat i no participa en la rotació de diapositives.

Si el **Mode Panoràmic** està activat, els interruptors queden bloquejats perquè una única imatge s'utilitza per a tota la composició.

#### Botons d'acció

- **Casella "Preferit"**: si la marques, en prémer **Acceptar** es desarà la composició actual com a preset.
- **Acceptar**: aplica els canvis a les pantalles. Si la casella **Preferit** està marcada, també desa el preset.
- **Actualitzar**: refresca la vista dels monitors des del motor.

### Mode d'edició

Prem el botó **Mode d'edició** amb la icona del llapis per assignar imatges manualment als monitors.

#### Arrossegar i deixar anar (Drag & Drop)

Pots arrossegar qualsevol imatge des de la galeria de miniatures i deixar-la anar sobre el monitor virtual al qual la vulguis assignar.

#### Panell d'opcions d'edició

Quan el mode d'edició està actiu apareixen opcions específiques per a la composició:

- **Estendre (Spanned)**: activa o desactiva el Mode Panoràmic per a aquesta composició.
- **Relació d'aspecte**: tria el mode d'ajust de les imatges.
- **Efectes**: aplica un efecte d'imatge a la composició.

Els canvis es poden previsualitzar mentre edites.

Aquests valors es desen juntament amb el preset i tenen prioritat sobre la configuració global quan s'utilitza aquell preset.

#### Botons d'acció en mode edició

- **Casella "Preferit"**: permet desar la composició editada com a preset.
- **Acceptar**: aplica els canvis i surt del mode d'edició. Si la casella està marcada, també desa el preset.
- **Actualitzar**: buida les imatges assignades als monitors perquè puguis reconstruir la composició des de zero.

## Miniatures

Aquesta secció mostra les imatges disponibles a la biblioteca de WMM. Les miniatures s'emmagatzemen a la memòria cau perquè la navegació sigui ràpida.

### Botó Actualitzar

Recarrega la vista de miniatures i reconstrueix les que siguin necessàries a partir de la biblioteca que WMM ja té sincronitzada.

Aquest botó **no substitueix Resincronitzar**. Si has afegit, eliminat, mogut o modificat fitxers originals fora de WMM, utilitza **Resincronitzar** per actualitzar primer la biblioteca.

### Botons H / V

Els botons **Horitzontal** i **Vertical** permeten saltar ràpidament al primer element de cada orientació dins de la galeria.

### Botó Preferits

Mostra una vista específica amb les imatges desades com a preferides, incloses les imatges que formen part dels teus **Presets**.

### Disposició i ordre

Les miniatures es mostren en un mosaic que s'adapta a l'amplada disponible.

L'ordre és:

- Primer les imatges **horitzontals**, amb les incorporades més recentment a la biblioteca en primer lloc.
- Després les imatges **verticals**, també amb les incorporades més recentment en primer lloc.

### Interacció amb les miniatures

Pots interactuar amb qualsevol miniatura de diverses maneres:

- **Doble clic**: obre la imatge original amb el visor predeterminat del sistema.
- **Clic dret**:
  - *"Afegir a preferits"*: afegeix la imatge a la llista de preferits.
  - *"Eliminar de preferits"*: l'elimina de la llista quan ja és preferida.
- **Arrossegar (Drag & Drop)**: en mode d'edició, pots arrossegar una miniatura sobre un monitor virtual per assignar-hi aquella imatge.

### Marc de preferit

Les imatges incloses a la llista de preferits es destaquen amb un marc de color verd.

# Preferits

El menú **Preferits** de WMM permet accedir ràpidament als presets desats i crear-ne de nous a partir de la composició actual.

### Switch "Només preferits"

Quan està activat, la presentació de diapositives utilitza únicament contingut desat com a preferit:

- **Mode síncron**: selecciona un preset i aplica la composició completa.
- **Mode asíncron**: utilitza imatges individuals de la llista de preferits.

Si actives **Només preferits** mentre la presentació de diapositives està apagada, WMM l'activa automàticament perquè la rotació pugui funcionar.

### Afegir un preset

Prem **"Afegir Preset a preferits"** per desar la composició actual.

S'obre un diàleg on pots indicar el nom del preset. WMM proposa un nom automàtic, per exemple *"Bookmark 01"*, que pots substituir pel que vulguis.

- **Nom en blanc**: WMM avisa i no desa el preset.
- **Nom repetit**: has de triar un nom diferent.
- **Desament del preset**: es desa la configuració actual dels monitors, incloses les imatges i les opcions associades a la composició.

### Llista de presets

Sota els controls apareix la llista de presets desats.

- **Carregar un preset**: prem sobre el seu nom per aplicar-lo. WMM atura el temporitzador si estava actiu i carrega la composició desada.
- **Eliminar un preset**: prem la icona de la paperera i confirma l'eliminació.

# Presentació de diapositives

Des d'aquest menú pots controlar el canvi automàtic de fons sense obrir el tauler de control.

### Switch "Activat / Desactivat"

L'interruptor principal encén o apaga el temporitzador de rotació.

- **Activat**: comença el compte enrere per al canvi següent.
- **Desactivat**: es manté la composició actual fins que tornis a activar la presentació o forcis una rotació manual.

L'estat se sincronitza automàticament amb el tauler de control.

### Interval

Defineix quants minuts han de passar entre canvis.

Segons l'entorn d'escriptori, el control es pot mostrar com a lliscador o mitjançant botons d'ajust. El valor mínim és d'1 minut i el màxim ve definit per **Freqüència màxima** al tauler de control.

Els canvis de l'interval s'apliquen al temporitzador de WMM.

# Monitors (Mode de Rotació)

Controla com es reparteixen els canvis de fons entre les pantalles.

- **ASYNC (One)**: els monitors canvien per torns. En cada cicle només un rep una imatge nova.
- **SYNC (All)**: tots els monitors canvien alhora.

El canvi de mode és immediat i no requereix reiniciar la presentació de diapositives.

# Mode Panoràmic (Spanned)

Activa o desactiva el fons panoràmic.

Quan està actiu, WMM utilitza una única imatge per construir una composició que cobreix el conjunt de monitors respectant-ne la posició i la geometria.

Aquesta opció només té efecte quan hi ha més d'un monitor actiu.

Mentre **Spanned** està activat, els interruptors individuals dels monitors queden bloquejats perquè la composició és comuna a totes les pantalles.

# Eines

El menú **Eines** reuneix els accessos operatius comuns de WMM:

- **Ajustaments**: obre el tauler de control.
- **Sincronitzar biblioteca**: revisa totes les fonts i actualitza la biblioteca.
- **Gestor d'instal·lació**: permet actualitzar, reinstal·lar o desinstal·lar WMM.
- **Visor del registre de depuració**: obre el visor d'activitat i diagnòstic.
- **Ajuda**: obre aquest manual.

## Sincronitzar Biblioteca

Revisa totes les fonts configurades i actualitza la biblioteca de WMM perquè coincideixi amb el contingut actual del disc.

La sincronització detecta imatges noves, modificades i eliminades, actualitza les referències necessàries i reconstrueix les miniatures que corresponguin.

És especialment útil després de fer canvis a les carpetes des de fora de WMM o quan apareix l'avís **"Resincronitzar fonts"**.

La sincronització no modifica ni elimina les imatges originals.

## Gestor d'instal·lació

**El Gestor d'instal·lació** permet fer les tasques de manteniment de WMM des d'una interfície gràfica.

La finestra mostra la versió instal·lada i l'entorn d'escriptori detectat.

### Actualitzar

Si hi ha una versió més recent, permet descarregar-la, validar-la i iniciar l'actualització.

### Reinstal·lar

Reinstal·la la versió actual per reparar o recuperar una instal·lació malmesa conservant les dades d'usuari que corresponguin.

### Desinstal·lar

Inicia el desinstal·lador de WMM i elimina l'aplicació i les seves integracions d'escriptori.

Abans de les operacions que ho necessitin, el terminal integrat pot demanar la contrasenya administrativa. Escriu-la directament en aquell terminal.

Durant una operació de manteniment, la resta de controls es mantenen bloquejats fins que acaba el procés.

## Visor del registre de depuració

El visor de logs mostra en temps real l'activitat de WMM i és útil per consultar què està fent el motor, el tauler o les integracions d'escriptori.

### Filtres

Pots filtrar les entrades per **Origen**, **Nivell** i **Motiu**, a més d'utilitzar la cerca de text.

### Auto-scroll

Manté la vista seguint automàticament les entrades noves del registre.

### Ordre invers

Permet mostrar primer les entrades més recents o mantenir l'ordre cronològic normal.

### Netejar registre

El botó de neteja buida el registre després de demanar confirmació.

El visor recorda les preferències d'**Auto-scroll**, **Ordre invers** i la mida de la finestra.

## Ajuda

Obre la finestra d'ajuda de WMM.

L'índex de navegació apareix a l'esquerra i el contingut Markdown formatat a la dreta perquè puguis saltar directament a la secció que necessitis.

# Quant a WMM Manager

Mostra informació bàsica sobre WMM, inclosa la versió instal·lada, el nom de l'aplicació i la llicència.
En alguns entorns d'escriptori també ofereix enllaços útils.

# Gestors de fitxers

WMM s'integra amb **Nemo**, **Nautilus**, **Dolphin** i **Caja** quan aquests gestors estan disponibles al sistema.

En fer clic dret sobre una imatge pots trobar accions de WMM per:

- **Afegir a preferits**.
- **Enviar a un monitor**.
- **Distribuir la imatge a totes les pantalles**.

Segons el gestor de fitxers, aquestes accions poden aparèixer agrupades dins de **WMM Manager** o com a accions individuals.

A MATE, la integració amb Caja també pot oferir una acció per distribuir la imatge actual des del menú contextual de l'escriptori.

# Dreceres de teclat

WMM registra l'acció **Fons següent** als mecanismes de dreceres de **Cinnamon**, **GNOME Shell**, **KDE Plasma 6** i **MATE**.

La combinació de tecles la tries tu des de la configuració de dreceres del teu escriptori.

## A Cinnamon

1. Obre **Configuració del sistema → Teclat → Dreceres de teclat**.
2. Entra a **Dreceres personalitzades**.
3. Busca **"WMM - Fons següent"**.
4. Assigna la combinació que prefereixis, per exemple `Ctrl+Alt+N`.

## A GNOME Shell

1. Obre la configuració de **Teclat** i les dreceres personalitzades.
2. Busca l'acció de WMM per a **Fons següent**.
3. Assigna la combinació que prefereixis.

## A KDE Plasma 6

1. Obre **Configuració del sistema → Dreceres**.
2. Busca **WMM Manager** i **Fons següent**.
3. Assigna la combinació de tecles que vulguis utilitzar.

## A MATE

1. Obre la configuració de **Dreceres de teclat** de MATE.
2. Busca **"WMM - Fons següent"**.
3. Assigna la combinació que prefereixis.

La drecera sol·licita una rotació manual utilitzant el mode i la configuració actuals de WMM.
