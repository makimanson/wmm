<!--
SPDX-FileCopyrightText: 2026 makimanson
SPDX-License-Identifier: GPL-3.0-or-later

WMM - Wallpaper Multi-Monitor Manager

HELP_ca.md -- Arxiu d'ajuda en català

WMM-Title: Ajuda
WMM-Contents: Continguts
-->

# Entorns d'escriptori

WMM disposa actualment d'integració completa amb **Cinnamon**, **GNOME Shell**, **KDE Plasma 6**, **MATE**, **XFCE** i **Windows 11**.

El tauler de control i les funcions principals són comuns a tots els entorns. Alguns controls poden variar lleugerament d'aspecte o d'ubicació segons l'escriptori, però comparteixen la mateixa configuració.

# Configuració

Obre el menú de WMM des de la seva icona al tauler o a la safata del sistema i selecciona **Configuració** per obrir el tauler de control.

## Opcions

Reuneix la configuració general de WMM en quatre grups: **Canviar el fons de pantalla en iniciar**, **Mode Panoràmic**, **Presentació de diapositives** i **Metadades d'imatge**.

Cada grup es pot plegar o desplegar prement-ne el títol. L'interruptor situat a la dreta activa o desactiva la funció corresponent, independentment de si els seus controls són visibles. WMM recorda l'estat de desplegament de les seccions.

### Icona Ajuda

Obre aquesta ajuda en una finestra independent.

### Icona Visor de Logs

Obre el visor de registres de depuració en una finestra separada. Mostra l'activitat de WMM i permet filtrar el registre.

### Icona Reiniciar

Reinicia el motor i el tauler de control per tornar a carregar WMM durant la sessió.

### Icona Plegar / Desplegar

Plega la columna lateral del tauler per deixar més espai a **Monitors** i **Miniatures**. En tornar a prémer-la, es recupera la vista completa. WMM recorda l'estat del tauler.

### Canviar el fons de pantalla en iniciar

L'interruptor de la capçalera determina què passa quan s'inicia WMM:

- **Activat**: el motor selecciona imatges noves i genera una composició nova.
- **Desactivat**: es conserva la darrera composició desada.

Els tres controls situats sota aquesta capçalera són independents de l'interruptor i també es poden utilitzar quan està desactivat.

#### Selecció per orientació del monitor

- **Activada**: WMM selecciona imatges que coincideixen amb l'orientació horitzontal o vertical del monitor.
- **Desactivada**: es poden utilitzar imatges de qualsevol orientació.

Aquest filtre intervé en la selecció d'imatges, però no força per si mateix un canvi de fons.

#### Rotació selectiva

Permet limitar la rotació automàtica a les carpetes que hagis marcat expressament a **Fonts d'imatges**.

Per preparar la selecció, fes clic dret sobre una carpeta activa i tria **Afegir a la rotació selectiva**. L'opció **Eliminar de la rotació selectiva** en retira la marca. Marcar carpetes no activa per si sol aquest mode.

- **Activada**: la rotació utilitza les carpetes actives i marcades per a la selecció.
- **Desactivada**: deixa d'aplicar-se el filtre selectiu, però es conserven les marques de les carpetes per tornar-lo a utilitzar.

L'interruptor només està disponible si hi ha almenys una carpeta activa i marcada. Si no queda cap carpeta que compleixi totes dues condicions, WMM desactiva la rotació selectiva.

En activar-la, WMM activa **Presentació de diapositives** si estava apagada i desactiva **Només preferits**, perquè tots dos modes de selecció són alternatius. En desactivar la rotació selectiva no es restaura automàticament el mode anterior.

#### Rotació

Defineix com es reparteixen els canvis de fons entre els monitors. L'etiqueta mostra el mode i el tipus de selecció utilitzat:

- **Síncron (Sync)**: tots els monitors canvien alhora. Amb **Només preferits** s'utilitzen presets complets.
- **Asíncron (Async)**: els monitors canvien per torns de manera independent. Amb **Només preferits** s'utilitzen imatges individuals de la llista de preferits.

En les transicions, el mode síncron utilitza un fos a negre i l'asíncron una fusió entre imatges, segons les possibilitats de l'entorn d'escriptori.

### Mode Panoràmic

L'interruptor activa o desactiva **Spanned**, que utilitza una única imatge estesa pel conjunt de monitors. Només té efecte quan hi ha més d'un monitor actiu.

Aquesta capçalera també agrupa els ajustos generals de composició, que continuen disponibles encara que **Spanned** estigui desactivat.

#### Relació d'aspecte

Controla com s'adapta la imatge a l'espai disponible:

- **Escalat (Scaled)**: manté les proporcions. L'espai sobrant s'omple amb el fons seleccionat.
- **Zoom**: cobreix tot l'espai sense deformar la imatge, retallant les parts que sobresurten.
- **Estirat (Stretched)**: ajusta la imatge a les dimensions exactes, encara que es pugui deformar.

#### Efecte d'imatge

- **Cap (None)**: no aplica cap efecte.
- **Sèpia (Sepia)**: dona a la imatge un to envellit.
- **Blanc i negre (Black and White)**: converteix la imatge a escala de grisos.

#### Efecte de fons

Defineix com s'omple l'espai que la imatge deixa lliure, principalment quan s'utilitza **Escalat**:

- **Difuminat (Blur)**: mostra una còpia desenfocada de la imatge.
- **Color**: utilitza el color sòlid o degradat configurat a **Color de fons**.

#### Color de fons

S'utilitza quan una imatge no omple tota la pantalla o quan un monitor no té cap imatge assignada:

- **Color sòlid**: permet triar un únic color.
- **Degradat horitzontal**: barreja dos colors d'esquerra a dreta.
- **Degradat vertical**: barreja dos colors de dalt a baix.

### Presentació de diapositives

El seu interruptor activa o desactiva el temporitzador de canvi automàtic. Els dos valors d'aquesta subsecció es poden ajustar sense necessitat d'engegar-lo.

#### Freqüència màxima

Estableix, en minuts, el valor màxim que es pot seleccionar per a l'interval de rotació des del menú de WMM.

#### Diapositives cada...

Defineix quants minuts passen entre canvis automàtics del fons de pantalla. El valor es coordina amb el màxim configurat perquè l'interval no el superi.

### Metadades d'imatge

Permet mostrar informació de la imatge sobre el fons de pantalla generat per WMM. L'interruptor de la capçalera activa o desactiva aquesta informació sense modificar els arxius originals.

#### Camps visibles

Prem **Seleccionar** per triar quines dades es mostraran. El diàleg organitza els camps per categories, com ara imatge, autor, origen, dates i geolocalització. Només es pot mostrar la informació disponible per a cada imatge.

- **Aplicar**: confirma la selecció i actualitza el resultat sense tancar el diàleg.
- **Desar**: confirma la selecció i tanca el diàleg.
- **Cancel·lar**: tanca el diàleg sense desar els canvis pendents des de la darrera aplicació.

#### Tipus de lletra i mida

Permet triar la tipografia i la mida utilitzades per mostrar les metadades.

#### Posició

Situa el bloc d'informació en una de les quatre cantonades: superior esquerra, inferior esquerra, superior dreta o inferior dreta.

#### Marge horitzontal

Ajusta la separació horitzontal del bloc respecte de la vora seleccionada, de **0 a 100 píxels**.

#### Marge vertical

Ajusta la separació vertical del bloc respecte de la vora seleccionada, de **0 a 100 píxels**.

#### Opacitat del fons

Controla l'opacitat del fons que apareix darrere les metadades, de **0 % (transparent)** a **100 % (opac)**.

Els canvis d'aspecte, posició, marges i opacitat es reflecteixen quan es recompon el fons de pantalla.

## Preferits

Gestiona les teves combinacions de fons preferides. Pots crear, carregar, modificar i eliminar presets. Un *preset* és una composició desada que pots recuperar en qualsevol moment.

### Interruptor "Només preferits"

Si l'actives, la presentació de diapositives utilitza exclusivament els teus preferits.

- En mode **síncron** s'utilitzen els presets desats.
- En mode **asíncron** s'utilitzen les imatges individuals de la llista de preferits.

### Quadre Presets (esquerra)

- **Carregar un preset als monitors**: fes clic dret sobre el nom del preset i selecciona *"Carregar als monitors"*. El preset es carregarà en mode d'edició perquè el puguis veure i modificar abans d'aplicar-lo.
- **Canviar el nom d'un preset**: fes un clic lent sobre el nom del preset. Quan el text es pugui editar, escriu el nom nou i prem Enter.
- **Eliminar un preset**: fes clic dret sobre el preset i selecciona *"Eliminar el preset"*. També el pots seleccionar i prémer el botó de la paperera.
- **Eliminar una imatge d'un preset**: fes clic dret sobre la imatge dins el preset i selecciona *"Eliminar la imatge"*. El monitor conservarà la seva posició al preset, però quedarà sense imatge.
- **Obrir una imatge del preset**: fes doble clic sobre la imatge per obrir-la amb el visor predeterminat del sistema.

### Quadre Preferits (dreta)

- **Afegir una imatge a preferits**: des de la galeria de miniatures, fes clic dret sobre una imatge i selecciona *"Afegir a preferits"*. També ho pots fer des dels gestors de fitxers compatibles amb WMM.
- **Seleccionar diverses imatges**: utilitza **Ctrl+clic** per a una selecció discontínua o **Majús+clic** per seleccionar un interval.
- **Eliminar una imatge de preferits**: fes clic dret sobre la imatge i selecciona *"Eliminar de preferits"*.
- **Obrir una imatge**: fes-hi doble clic per obrir-la amb el visor d'imatges predeterminat del sistema.

### Botons d'eliminació

Tant el quadre de Presets com el de Preferits tenen un botó amb la icona de paperera a la part inferior dreta.

El botó elimina l'element seleccionat en aquell moment. Si hi ha diverses imatges seleccionades a la llista de preferits, les elimina totes de la llista.

## Fonts d'imatges

Des d'aquí pots afegir, eliminar i gestionar les carpetes que WMM utilitza com a biblioteca d'imatges.

Si una font és recursiva, també se'n mostren les subcarpetes i pots decidir quines continuen actives.

En aquesta secció, **WMM no elimina mai les carpetes ni les imatges originals del disc**. Les operacions de neteja només afecten la biblioteca interna i les miniatures desades a la memòria cau.

### Botó "Afegir una font"

Obre un diàleg per seleccionar una carpeta del sistema.

- **Incloure subcarpetes (Recursiu)**: activa-ho si vols que WMM inclogui també les subcarpetes d'aquesta font.
- Si ho deixes desactivat, només s'utilitzaran les imatges situades directament a la carpeta arrel.
- En prémer **Afegir**, WMM registra la font nova, en sincronitza el contingut i actualitza la galeria.
- Quan acaba l'operació, les imatges disponibles apareixen a la secció **Miniatures**.

### Carpeta Online

L'entrada **Online** de l'arbre de fonts permet vincular un directori del sistema a les imatges descarregades mitjançant la funcionalitat Online.

Per establir-ne la ubicació, selecciona **Online** a l'arbre i prem **Afegir una font**. S'obrirà el selector de carpetes per triar el directori que vols utilitzar.

Si ja hi ha un directori vinculat, el mateix procediment permet modificar-ne la ubicació.

Aquesta operació estableix o canvia la carpeta utilitzada per Online sense eliminar els fitxers originals de la ubicació anterior.

### Botó "Eliminar una font"

Elimina la font seleccionada de la biblioteca de WMM.

Abans de fer-ho, es mostra un diàleg de confirmació. Si acceptes:

- La font desapareix de la llista.
- Les seves imatges deixen d'estar disponibles per a WMM.
- Es retiren de la biblioteca i de la memòria cau les dades associades a aquesta font.

Els fitxers originals es mantenen intactes al disc.

### Botó "Resincronitzar"

Revisa les fonts configurades i actualitza la biblioteca segons el contingut real de les carpetes.

Utilitza'l quan:

- hagis afegit, eliminat, mogut o canviat el nom d'imatges fora de WMM;
- hagis modificat imatges amb un altre programa;
- hagis canviat l'estructura de les carpetes;
- aparegui l'avís **"Sources need resynchronization"**;
- vulguis reconciliar globalment l'estat de totes les fonts.

Durant la sincronització, WMM detecta les imatges noves, modificades o eliminades i actualitza la biblioteca i les miniatures necessàries.

### Avís "Sources need resynchronization"

Aquest avís indica que la configuració actual de les fonts i el contingut que WMM té preparat per mostrar encara no coincideixen del tot.

No és un error. Pot aparèixer, per exemple, després d'activar o desactivar carpetes, canviar l'opció **Recursiu** o reactivar una carpeta la memòria cau de la qual ja s'havia eliminat.

Prem **Resincronitzar** per actualitzar globalment la biblioteca.

Si només vols recuperar una subcarpeta activa que no té memòria cau, pots utilitzar **Generar miniatures** des del seu menú contextual.

### Navegació per l'arbre de carpetes

#### Seleccionar una carpeta

En seleccionar una carpeta a l'arbre, la secció **Miniatures** mostra únicament les imatges corresponents a aquesta carpeta.

Per tornar a visualitzar tota la biblioteca, selecciona **TOTS**.

#### Doble clic sobre una carpeta

Obre la carpeta amb el gestor de fitxers predeterminat del sistema.

#### Clic dret sobre una carpeta

El menú contextual ofereix les accions disponibles segons el tipus i l'estat de la carpeta:

- **Activar / Desactivar carpeta**: canvia si les seves imatges formen part de la biblioteca activa. El canvi de visibilitat és immediat i no inicia per si sol una sincronització completa.
- **Activar subcarpetes / Desactivar subcarpetes**: en una font recursiva, permet canviar alhora l'estat de les seves subcarpetes.
- **Generar miniatures**: està disponible per a una subcarpeta activa que encara no té contingut preparat a la memòria cau. Processa únicament aquesta subcarpeta.
- **Eliminar memòria cau**: apareix per a carpetes inactives. Elimina de WMM la memòria cau associada a aquesta carpeta, però no toca les imatges originals.
- **Afegir a la rotació selectiva / Eliminar de la rotació selectiva**: disponible únicament per a carpetes actives. Permet incloure o excloure la carpeta i totes les seves subcarpetes de la rotació selectiva. Aquesta acció no activa ni desactiva el mode, que es controla des d'**Opcions**. Les carpetes inactives no participen en la rotació, encara que conservin la seva marca.

Si es reactiva una carpeta mentre encara existeix la seva memòria cau, WMM la pot reutilitzar immediatament.

Si es reactiva després d'haver eliminat la memòria cau, quedarà activa, però les seves imatges no apareixeran fins que utilitzis **Resincronitzar** o **Generar miniatures**.

### Activar / Desactivar la recursivitat

La columna **Recursiu** apareix a les fonts arrel.

- **Activat**: les subcarpetes formen part de la font.
- **Desactivat**: WMM utilitza únicament la carpeta arrel.

El canvi es reflecteix immediatament a l'arbre i a la visibilitat de les imatges.

Activar **Recursiu** permet a WMM descobrir les subcarpetes, però no obliga a reconstruir automàticament les imatges o miniatures que ja no siguin a la memòria cau. En aquest cas, pots fer servir **Resincronitzar** per a tota la biblioteca o **Generar miniatures** per a una subcarpeta concreta.

## Monitors

Aquí es mostren els teus monitors com a miniatures. La secció s'actualitza amb els canvis de fons, geometria i estat de les pantalles.

### Botonera d'alineació

A la capçalera trobaràs tres botons: `[` , `•` i `]`. Permeten canviar l'alineació horitzontal del bloc de monitors dins la finestra:

- **`[`**: alineació a l'esquerra.
- **`•`**: alineació centrada.
- **`]`**: alineació a la dreta.

És útil quan tens monitors amb geometries molt diferents i vols ajustar visualment la previsualització.

### Mode normal

En mode normal, la secció mostra una miniatura de cada monitor amb la imatge assignada i un interruptor per activar-lo o desactivar-lo.

#### Interruptors de monitor

- **Activat**: el monitor mostra la imatge assignada. Si no en té cap, WMM en pot assignar una segons la seva orientació.
- **Desactivat**: el monitor s'omple amb el color de fons seleccionat i no participa en la rotació de diapositives.

Si el **Mode Panoràmic** està activat, els interruptors queden bloquejats perquè s'utilitza una única imatge per a tota la composició.

#### Botons d'acció

- **Casella "Preferit"**: si la marques, en prémer **Acceptar** es desarà la composició actual com a preset.
- **Acceptar**: aplica els canvis a les pantalles. Si la casella **Preferit** està marcada, també desa el preset.
- **Actualitzar**: actualitza la vista dels monitors a partir del motor.

### Mode d'edició

Prem el botó **Mode d'edició**, amb la icona del llapis, per assignar imatges manualment als monitors.

#### Arrossegar i deixar anar (Drag & Drop)

Pots arrossegar qualsevol imatge des de la galeria de miniatures i deixar-la anar sobre el monitor virtual al qual la vulguis assignar.

#### Tauler d'opcions d'edició

Quan el mode d'edició està actiu, apareixen opcions específiques per a la composició:

- **Estendre (Spanned)**: activa o desactiva el Mode Panoràmic per a aquesta composició.
- **Relació d'aspecte**: tria com s'ajusten les imatges.
- **Efectes**: aplica un efecte d'imatge a la composició.

Pots previsualitzar els canvis mentre edites.

Aquests valors es desen juntament amb el preset i tenen prioritat sobre la configuració global quan s'utilitza aquell preset.

#### Botons d'acció en mode d'edició

- **Casella "Preferit"**: permet desar la composició editada com a preset.
- **Acceptar**: aplica els canvis i surt del mode d'edició. Si la casella està marcada, també desa el preset.
- **Actualitzar**: buida les imatges assignades als monitors perquè puguis reconstruir la composició des de zero.

## Miniatures

Aquesta secció mostra les imatges disponibles a la biblioteca de WMM. Les miniatures es desen a la memòria cau per agilitzar la navegació.

### Botó Actualitzar

Torna a carregar la vista de miniatures i reconstrueix les que calgui a partir de la biblioteca que WMM ja té sincronitzada.

Aquest botó **no substitueix Resincronitzar**. Si has afegit, eliminat, mogut o modificat fitxers originals fora de WMM, utilitza **Resincronitzar** per actualitzar primer la biblioteca.

### Botons H / V

Els botons **Horitzontal** i **Vertical** permeten anar ràpidament al primer element de cada orientació dins la galeria.

### Botó Preferits

Mostra una vista específica amb les imatges desades com a preferides, incloses les imatges que formen part dels teus **Presets**.

### Botó Online

Obre el cercador de fons de pantalla a Internet. Permet consultar imatges de serveis externs, descarregar-les i incorporar-les a la biblioteca de WMM.

Online disposa d'una galeria independent de les miniatures locals. Les cerques no modifiquen la biblioteca ni les imatges originals.

#### Ús responsable

En accedir a Online es presenta el document **Ús responsable de serveis i recursos de tercers**, que explica els principis d'integració, les condicions dels proveïdors i les responsabilitats relacionades amb els seus continguts.

Per continuar, marca **He llegit i entès aquest document** i prem **Acceptar**.

La casella **No tornar a mostrar** permet ometre aquesta pantalla en accessos posteriors, una vegada hagis llegit i entès el document.

Pots tornar-ne a consultar el contingut des de **Quant a WMM > Llicències**.

#### Cerca i filtres

El cercador permet combinar tres criteris:

- **Cercar**: introdueix paraules o termes relacionats amb les imatges que vols trobar, **en anglès**. També pots cercar sense introduir cap text.
- **Relació d'aspecte**: selecciona qualsevol proporció, una orientació horitzontal o vertical, o una proporció concreta, com 16:9, 21:9, 32:9 o 9:16.
- **Proveïdor**: selecciona **Qualsevol** per consultar tots els proveïdors disponibles, o tria'n un individualment.

Actualment WMM integra **Wallhaven** i **Alpha Coders**.

Prem **Cercar** o Enter per iniciar la consulta.

El botó de cerca torna a estar disponible quan modifiques algun criteri. Els filtres s'apliquen segons les possibilitats de cada proveïdor.

#### Resultats i navegació

Les imatges trobades apareixen progressivament com a miniatures, indicant-ne la resolució i la procedència.

Quan es consulten diversos proveïdors, els resultats s'agrupen per servei. Pots prémer el nom o el logotip del proveïdor per visitar-ne el web.

Cada miniatura disposa d'un accés a la seva pàgina d'origen, que s'obre al navegador predeterminat.

El botó **Carregar més** permet obtenir la pàgina de resultats següent sense eliminar les anteriors.

Si modifiques els criteris de cerca, hauràs de prémer **Cercar** de nou abans de continuar carregant resultats.

#### Carpeta de descàrregues Online

Les imatges descarregades es desen a la carpeta **Online**, la ubicació de la qual es configura des de **Fonts d'imatges**.

Per establir-la o modificar-la, selecciona l'entrada **Online** a l'arbre de fonts i utilitza el botó **Afegir una font**.

Si no hi ha una carpeta Online vàlida configurada, WMM n'informa i no inicia la descàrrega.

Desvincular aquesta carpeta de WMM no elimina els seus fitxers originals del disc.

#### Selecció i descàrrega

Les miniatures que permeten descarregar la imatge original mostren un botó de selecció.

Pots seleccionar fins a **5 imatges per lot**. El botó **Descarregar** mostra quantes imatges has seleccionat i permet iniciar-ne la descàrrega.

Durant l'operació es mostra el progrés de cada fitxer. WMM respecta les limitacions dels proveïdors i introdueix una pausa preventiva entre descàrregues consecutives.

Les imatges descarregades correctament s'identifiquen com a **Descarregades** i deixen d'estar disponibles per a una nova selecció, evitant descàrregues redundants.

En acabar, WMM sol·licita automàticament la sincronització de les fonts per incorporar les imatges noves a la biblioteca i generar-ne les miniatures.

Les imatges incorporades queden disponibles per a les funcions habituals de WMM.

#### Arrossegar imatges als monitors

En **Mode d'edició**, pots arrossegar una miniatura Online directament sobre un monitor virtual.

WMM prepara la imatge original per previsualitzar-la a la composició, sense exigir que la descarreguis prèviament mitjançant el botó **Descarregar**.

En prémer **Acceptar** a l'editor, la imatge s'incorpora definitivament a la carpeta Online i se sincronitza amb la biblioteca.

#### Claus API

El botó **Claus API** obre el formulari de gestió de credencials personals per als proveïdors disponibles.

A la part superior trobaràs un apartat **TIP** desplegable amb informació sobre l'ús d'aquestes claus.

Cada proveïdor disposa d'un camp informatiu i dues accions alternatives:

- **Examinar**: permet seleccionar un fitxer que contingui la teva clau API personal.
- **Desvincular**: elimina l'associació amb aquest fitxer, sense modificar-lo ni esborrar-lo.

WMM comprova la validesa del contingut abans de vincular-lo. Les claus no es desen directament a la configuració: només es conserva la ruta del fitxer corresponent.

L'ús de claus personals depèn de les característiques i condicions de cada proveïdor.

### Disposició i ordre

Les miniatures es mostren en un mosaic que s'adapta a l'amplada disponible.

Les imatges s'organitzen primer per orientació:

- **Horitzontals (H)**: es mostren en primer lloc.
- **Verticals (V)**: es mostren a continuació.

Dins de cada grup, les imatges s'ordenen per data d'incorporació a la biblioteca de WMM, mostrant primer les incorporacions més recents.

### Interacció amb les miniatures

Pots interactuar amb qualsevol miniatura de diverses maneres:

- **Doble clic**: obre la imatge original amb el visor predeterminat del sistema.
- **Clic dret**:
  - *"Afegir a preferits"*: afegeix la imatge a la llista de preferits.
  - *"Eliminar de preferits"*: l'elimina d'aquesta llista quan ja és preferida.
- **Arrossegar (Drag & Drop)**: en mode d'edició, pots arrossegar una miniatura sobre un monitor virtual per assignar-li aquesta imatge.

### Marc de preferit

Les imatges incloses a la llista de preferits es destaquen amb un marc el color del qual s'adapta al tema visual actiu.

# Icona de WMM (tauler o safata del sistema)

La icona de WMM permet accedir als seus controls i eines sense obrir el tauler de configuració.

- **Clic esquerre**: obre el menú principal.
- **Clic central**: sol·licita el fons de pantalla següent.
- **Clic dret**: obre el menú contextual.

## Menú principal

Reuneix els controls de rotació, preferits, presentació de diapositives, mode panoràmic i metadades d'imatge, a més de l'acció per canviar el fons immediatament.

### Preferits

El menú **Preferits** de WMM permet accedir ràpidament als presets desats i crear-ne de nous a partir de la composició actual.

#### Interruptor "Només preferits"

Quan està activat, la presentació de diapositives utilitza únicament contingut desat com a preferit:

- **Mode síncron**: selecciona un preset i aplica tota la composició.
- **Mode asíncron**: utilitza imatges individuals de la llista de preferits.

Si actives **Només preferits** mentre la presentació de diapositives està apagada, WMM l'activa automàticament perquè la rotació pugui funcionar.

#### Afegir un preset

Prem **"Afegir preset a preferits"** per desar la composició actual.

S'obre un diàleg on pots indicar el nom del preset. WMM proposa un nom automàtic, per exemple *"Bookmark 01"*, que pots substituir pel que vulguis.

- **Nom en blanc**: WMM t'avisa i no desa el preset.
- **Nom repetit**: has de triar un nom diferent.
- **Desament del preset**: es desa la configuració actual dels monitors, incloent-hi les imatges i opcions associades a la composició.

#### Llista de presets

Sota els controls apareix la llista de presets desats.

- **Carregar un preset**: prem-ne el nom per aplicar-lo. WMM atura el temporitzador si estava actiu i carrega la composició desada.
- **Eliminar un preset**: prem la icona de la paperera i confirma'n l'eliminació.

### Presentació de diapositives

Des d'aquest menú pots controlar el canvi automàtic de fons sense obrir el tauler de control.

#### Interruptor "Activat / Desactivat"

L'interruptor principal encén o apaga el temporitzador de rotació.

- **Activat**: comença el compte enrere per al canvi següent.
- **Desactivat**: es manté la composició actual fins que tornis a activar la presentació o forcis una rotació manual.

L'estat se sincronitza automàticament amb el tauler de control.

#### Interval

Permet indicar quants minuts han de passar entre canvis.

Segons l'entorn d'escriptori, el control es pot mostrar com un lliscador o mitjançant botons d'ajust. El valor mínim és d'1 minut i el màxim es defineix amb **Freqüència màxima** al tauler de control.

Els canvis de l'interval s'apliquen al temporitzador de WMM.

### Monitors (Mode de Rotació)

Controla com es reparteixen els canvis de fons entre les pantalles.

- **ASYNC (One)**: els monitors canvien per torns. En cada cicle, només un rep una imatge nova.
- **SYNC (All)**: tots els monitors canvien alhora.

El canvi de mode és immediat i no requereix reiniciar la presentació de diapositives.

### Mode Panoràmic (Spanned)

Activa o desactiva el fons panoràmic.

Quan està actiu, WMM utilitza una única imatge per construir una composició que cobreix el conjunt de monitors respectant-ne la posició i la geometria.

Aquesta opció només té efecte quan hi ha més d'un monitor actiu.

Mentre **Spanned** està activat, els interruptors individuals dels monitors queden bloquejats perquè la composició és comuna a totes les pantalles.

### Metadades d'imatge

Permet mostrar o ocultar la informació de la imatge directament des del menú principal de WMM, sense necessitat d'obrir el tauler de control.

- **Activat**: mostra les metadades segons els camps, tipus de lletra, posició i altres opcions configurades.
- **Desactivat**: oculta les metadades sense perdre'n la configuració.

Els canvis s'apliquen al fons de pantalla i se sincronitzen amb la secció **Metadades d'imatge** del tauler de control.

### Fons següent

Sol·licita un canvi immediat del fons de pantalla utilitzant el mode de rotació i la configuració actuals de WMM.

- **Clic esquerre**: sol·licita el fons següent sense haver d'esperar el temporitzador.
- **Clic dret**: obre el formulari per configurar la drecera de teclat.

Si hi ha una combinació de tecles assignada, es mostra a la dreta de "Fons següent".

#### Dreceres de teclat

WMM permet assignar una drecera global per sol·licitar el fons de pantalla següent sense obrir el menú principal.

Per configurar-la, fes clic dret sobre "Fons següent". S'obrirà un formulari que mostra la combinació registrada actualment i permet modificar-la.

- **Assignar o canviar**: prem la combinació desitjada al camp de captura. No cal escriure-la manualment.
- **Esborrar**: buida el camp de captura per retirar la drecera actual o introduir-ne una de nova.
- **Acceptar**: valida i registra la combinació seleccionada. Si el camp és buit, elimina la drecera registrada.
- **Cancel·lar**: descarta els canvis i conserva la combinació anterior.

El formulari informa si una combinació no està admesa, és incompleta o es detecta que ja s'utilitza. En aquests casos, hauràs de triar una altra combinació.

Durant la configuració, la drecera anterior se suspèn temporalment per permetre'n la modificació. Si cancel·les l'operació, WMM la restaura automàticament.

Els canvis confirmats es conserven entre sessions i la combinació registrada es mostra al costat de "Fons següent" al menú principal.

## Menú contextual

El menú contextual reuneix les eines de configuració, manteniment i informació de WMM:

- **Configuració**: obre el tauler de control.
- **Sincronitzar biblioteca**: revisa totes les fonts i actualitza la biblioteca.
- **Gestor d'instal·lació**: disponible a Linux i Windows Open Code. Permet realitzar les operacions de manteniment de WMM. La versió compilada de Windows utilitza Inno Setup.
- **Visor de registres de depuració**: obre el visor d'activitat i diagnòstic.
- **Ajuda**: obre aquest manual.
- **Iniciar WMM amb Windows** (només Windows): activa o desactiva l'inici automàtic de WMM en començar la sessió.
- **Quant a WMM Manager**: mostra informació sobre l'aplicació.
- **Sortir de WMM**: tanca WMM.

### Sincronitzar biblioteca

Revisa totes les fonts configurades i actualitza la biblioteca de WMM perquè coincideixi amb el contingut actual del disc.

La sincronització detecta imatges noves, modificades i eliminades, actualitza les referències necessàries i reconstrueix les miniatures que corresponguin.

És especialment útil després de fer canvis a les carpetes des de fora de WMM o quan apareix l'avís **"Resincronitzar fonts"**.

La sincronització no modifica ni elimina les imatges originals.

### Gestor d'instal·lació

WMM disposa de mecanismes de manteniment diferents segons el sistema operatiu i el tipus d'instal·lació.

#### Linux

El Gestor d'instal·lació permet actualitzar, reinstal·lar o desinstal·lar WMM mitjançant una interfície gràfica.

La finestra mostra la versió instal·lada i l'entorn d'escriptori detectat.

- **Actualitzar**: comprova si s'ha publicat una versió més recent a GitHub i permet descarregar-la i instal·lar-la.
- **Reinstal·lar**: reinstal·la la versió actual utilitzant una còpia neta del paquet de reparació preparat durant la instal·lació.
- **Desinstal·lar**: elimina WMM, les seves integracions amb l'escriptori, la configuració i les dades associades.

Les operacions s'executen mitjançant els scripts d'instal·lació i desinstal·lació de WMM.

El gestor incorpora un terminal on pots consultar el progrés i els missatges de l'operació. Si calen permisos administratius, introdueix la contrasenya directament en aquest terminal.

Durant una operació de manteniment, els altres controls queden bloquejats fins que acaba el procés.

#### Windows Open Code

La distribució Open Code disposa d'un gestor de manteniment propi, desenvolupat en PowerShell i accessible des del menú contextual de WMM.

La finestra mostra la versió instal·lada, la versió del paquet local i la darrera versió disponible a GitHub, quan es pot consultar.

Les operacions disponibles depenen de les versions detectades i dels paquets disponibles:

- **Instal·lar**: instal·la WMM des d'una distribució local vàlida quan encara no està instal·lat.
- **Actualitzar**: instal·la una versió més recent, procedent del paquet local o de GitHub.
- **Reinstal·lar**: recupera la versió instal·lada utilitzant el paquet local corresponent o la còpia de reparació de WMM.
- **Tornar a una versió anterior**: permet instal·lar una versió més antiga quan se'n disposa de la distribució local.
- **Desinstal·lar**: elimina WMM, les seves integracions amb Windows, la configuració i la memòria cau.

El gestor demana confirmació abans d'iniciar cada operació i identifica la versió i la procedència del paquet seleccionat.

Si només falta el runtime d'una distribució local vàlida, WMM pot oferir-ne la descàrrega des de GitHub, amb l'autorització prèvia de l'usuari.

Les operacions mostren el seu progrés en una finestra independent. Els fitxers originals dels fons de pantalla no s'eliminen durant la desinstal·lació.

#### Windows — Inno Setup

La distribució compilada de Windows utilitza l'instal·lador Inno Setup i no inclou el Gestor d'instal·lació d'Open Code.

- **Instal·lar**: executa l'instal·lador de WMM i segueix les indicacions de l'assistent.
- **Actualitzar o reinstal·lar**: executa l'instal·lador corresponent a la versió que vols instal·lar. Inno Setup gestiona la substitució dels fitxers de l'aplicació.
- **Desinstal·lar**: utilitza l'opció de desinstal·lació de WMM des de Windows o l'accés corresponent del menú Inici.

El desinstal·lador d'Inno Setup permet triar, mitjançant dues caselles independents, si vols eliminar:

- **Memòria cau de miniatures**: els fitxers temporals generats per visualitzar les imatges.
- **Dades de configuració de WMM**: informació persistent com preferències, fonts, preferits, perfils i historial.

Aquestes opcions apareixen abans d'iniciar la desinstal·lació i permeten decidir quines dades addicionals s'han de retirar. Alguns fitxers auxiliars de configuració s'eliminen com a part de la neteja habitual.

La desinstal·lació no elimina mai les imatges originals de l'usuari.

### Visor de registres de depuració

El visor de registres mostra en temps real l'activitat de WMM i és útil per consultar què estan fent el motor, el tauler o les integracions d'escriptori.

#### Filtres

Pots filtrar les entrades per **Origen**, **Nivell** i **Motiu**, a més d'utilitzar la cerca de text.

#### Desplaçament automàtic

Manté la vista seguint automàticament les entrades noves del registre.

#### Ordre invers

Permet mostrar primer les entrades més recents o mantenir l'ordre cronològic habitual.

#### Netejar registre

El botó de neteja buida el registre després de demanar confirmació.

El visor recorda les preferències de **Desplaçament automàtic**, **Ordre invers** i la mida de la finestra.

### Ajuda

Obre aquesta finestra d'ajuda de WMM.

L'índex de navegació apareix a l'esquerra i el contingut Markdown formatat a la dreta, perquè puguis anar directament a la secció que necessitis.

### Quant a WMM Manager

Mostra informació bàsica sobre WMM, incloent-hi la versió instal·lada, el nom de l'aplicació i la llicència.
En alguns entorns d'escriptori també ofereix enllaços útils.

# Gestors de fitxers

WMM s'integra amb **Nemo**, **Nautilus**, **Dolphin**, **Caja**, **Thunar** i **Explorer** quan aquests gestors estan disponibles al sistema.

En fer clic dret sobre una imatge pots trobar accions de WMM per:

- **Afegir a preferits**.
- **Enviar a un monitor**.
- **Estendre la imatge per totes les pantalles**.

Segons el gestor de fitxers, aquestes accions poden aparèixer agrupades dins de **WMM Manager** o com a accions individuals.

A MATE, la integració amb Caja també pot oferir una acció per estendre la imatge actual des del menú contextual de l'escriptori.

# Dreceres de teclat

WMM registra l'acció **Fons següent** als mecanismes de dreceres de **Cinnamon**, **GNOME Shell**, **KDE Plasma 6**, **MATE** i **XFCE**.

Pots configurar la combinació de tecles des de les eines de dreceres del teu entorn d'escriptori.

Des de WMM 2.0, també pots assignar, modificar o eliminar la drecera directament des del menú principal de la icona de WMM. Fes clic dret sobre **Fons següent** per obrir el formulari de configuració.

A continuació s'explica com gestionar la drecera des de cada entorn d'escriptori Linux.

## A Cinnamon

1. Obre **Configuració del sistema → Teclat → Dreceres de teclat**.
2. Entra a **Dreceres personalitzades**.
3. Cerca **"WMM - Fons següent"**.
4. Assigna la combinació que prefereixis, per exemple `Ctrl+Alt+N`.

## A GNOME Shell

1. Obre la configuració de **Teclat** i les seves dreceres personalitzades.
2. Cerca l'acció de WMM per a **Fons següent**.
3. Assigna la combinació que prefereixis.

## A KDE Plasma 6

1. Obre **Configuració del sistema → Dreceres**.
2. Cerca **WMM Manager** i **Fons següent**.
3. Assigna la combinació de tecles que vulguis utilitzar.

## A MATE

1. Obre la configuració de **Dreceres de teclat** de MATE.
2. Cerca **"WMM - Fons següent"**.
3. Assigna la combinació que prefereixis.

## A XFCE

1. Obre **Configuració → Teclat → Dreceres d'aplicació**.
2. Localitza l'ordre **wmm-next.sh**, registrada per WMM.
3. Selecciona l'entrada i edita'n la drecera.
4. Assigna la combinació de tecles que prefereixis.

La drecera sol·licita una rotació manual utilitzant el mode i la configuració actuals de WMM.
