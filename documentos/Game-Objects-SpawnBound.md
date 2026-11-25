# SpawnBound — Detalhamento dos Game Objects

## Introdução

Este documento apresenta os principais Game Objects de **SpawnBound**, sua função no jogo, seus estados, ações e atributos. A organização começa pelo mundo que os contém. Em seguida, os objetos são agrupados em cinco famílias: personagens, recursos, estruturas e construções, elementos do mundo e elementos de eventos.

Uma árvore ajuda a entender essa divisão. De pé, ela ocupa uma célula e bloqueia o caminho. Ao receber golpes, perde resistência. Quando cai, a célula fica livre e duas madeiras entram no inventário. A árvore pertence ao mundo, a madeira pertence à mochila e o machado determina quanto trabalho cada golpe realiza. O catálogo descreve essas relações na versão final da campanha.

**Bruno Vicente Dias e João Vitor Battigaglia Fernandes** · Laboratório de Programação de Jogos · 25 de novembro de 2026

## Estrutura e composição do mundo

| Conceito do projeto | Representação final | Função |
|---|---|---|
| Mundo e arquipélago | `GameSession`, `IslandSpec`, `WorldSpaces` | A sessão reúne as ilhas da seed, o jogador e os espaços gerados. Mantém a ilha principal como ponto de retorno. |
| Ilha | `IslandSpec` e um `World` exterior | A especificação guarda nome, tamanho e seed. O exterior contém o relevo, os objetos colocados e os acessos ao interior da casa ou à mina. |
| Região | Bioma de cada célula | Floresta, campina e deserto orientam a distribuição da vegetação, dos recursos e das criaturas. A exploração revela o mapa por posição. |
| Célula do mapa | `GridPos`, `Tile` e `TileMap` | A coordenada localiza o terreno e o objeto que ocupa aquela posição. Tipo de piso, altura, profundidade da água e obstáculos determinam a passagem. |

| Espaço ou elemento | Estado e função na campanha |
|---|---|
| Ilha principal | Por padrão, 128 × 128 células, com uma faixa de oceano de 16 células por lado. A clareira da base reúne os acessos à casa e à horta. O moinho fica no morro e o cais na costa. |
| Ilha do barco | 96 × 96 células. Tem cais de desembarque, mina, fauna, pedra de viagem e arena. O jogador encontra nesta ilha os oito menires e o Guardião. |
| Floresta, campina e deserto | Os biomas influenciam vegetação e fauna. A floresta concentra árvores e cervos. A campina favorece rebanhos e arbustos. No deserto aparecem cactos, palmeiras, arenito, tatus e tocas de sandworm quando o terreno comporta a espécie. |
| Casa e mina | O portal resolve um destino e uma posição de chegada. A casa é um interior mobiliável. Cada ilha tem sua própria mina com relevo, veios e iluminação de orientação. Ao sair e voltar, o jogo conserva alterações como uma rocha já golpeada. |
| Parede escavável | A picareta acumula dano na célula da mina. A quebra produz uma pedra, concede 4 XP e converte a parede em piso. A borda externa é protegida. |
| Orientação e descoberta | As tochas-guia indicam a rota de saída da mina. No exterior, a exploração registra as áreas visitadas por ilha para o mapa aberto com M. |

## Estados de progressão

No planejamento, descobrir, desbloquear e concluir eram estados de regiões e ilhas. Na campanha, é possível ler o avanço diretamente no cenário. O cais passa de ruína a ponto de embarque, a segunda ilha entra no registro de visitas e a derrota do Guardião fica gravada naquela ilha. A linha de objetivos acompanha oito marcos.

| Etapa mostrada | Condição efetiva |
|---|---|
| 1. Coletar 10 madeiras | Ter 10 madeiras na mochila. A sessão olha o saldo atual. |
| 2. Melhorar uma ferramenta para pedra | Possuir ao menos uma ferramenta de pedra, cobre ou quartzo. |
| 3. Juntar 3 carvões na mina | Ter 3 carvões. O carvão do arenito do deserto também satisfaz a condição. |
| 4. Montar uma fogueira | Existir uma fogueira colocada no mundo atual. Fabricar o item e deixá-lo na mochila ainda não conclui a etapa. |
| 5. Assar uma carne | Ter um produto assado da lista de receitas da fogueira. Um peixe assado também conta. |
| 6. Consertar o cais | O cais da ilha principal estar na variante restaurada. |
| 7. Navegar até outra ilha | A sessão ter registrado a visita a outra ilha. |
| 8. Derrotar o Guardião | Estar registrada a vitória em um dos mundos da sessão. O painel final mostra tempo, ilhas visitadas e corações. |

O guia mantém as etapas concluídas. Os marcos permanentes de reparo, viagem e vitória também fazem o guia alcançar o progresso já realizado. Assim, um jogador que prioriza a travessia não fica preso a uma orientação de cozinha anterior. [Condições e avanço](../src/spawnbound/domain/guide.py)

## Game Objects

### Personagens

O protagonista, a fauna e o chefe podem ocupar o mesmo cenário e participar de um combate. Cada um guarda os dados de que precisa para agir. Os estados abaixo descrevem o que acontece durante a partida.

| Objeto e representação | Função | Estados principais | Ações e atributos |
|---|---|---|---|
| Protagonista · `Player` | Personagem controlado por clique | Em movimento, coletando, atacando, descansando, ferido ou derrotado | Move-se, equipa ferramentas, gasta energia, come e ganha XP. Guarda posição, direção, vida, energia, nível e inventário. |
| Criatura · `Mob` | Animal ou inimigo com comportamento por espécie | Em repouso, alerta, em fuga ou ataque, conforme a espécie | Usa posição, vida, alvo e tempo de ação para perseguir, fugir, golpear ou defender-se. Pode conceder itens e XP. |
| Guardião de Pedra · `Mob` e `Guardian` | Chefe da ilha secundária | Adormecido, preparando golpe, atacando, vulnerável e derrotado | O estado do combate controla avisos e janelas de ataque. A ilha guarda a vitória. |

O personagem começa com 8 corações, 100 de energia e quatro ferramentas de madeira. A primeira subida de nível exige 100 XP, a segunda 150 e a terceira 200. Ao perder o último coração, ele volta à clareira da ilha principal com a mochila preservada e a vida e a energia recuperadas.

| Criatura | Vida | Encontro e reação | Recompensa pela derrota |
|---|---:|---|---|
| Galinha | 2 | Animal de rebanho. Um golpe afugenta galinhas próximas. | 1 carne, 5 XP |
| Porco | 4 | Animal de rebanho. Porcos próximos também fogem ao ataque. | 2 carnes, 5 XP |
| Cervo | 14 | Na floresta, reage ao ataque com coice e investida. A chifrada de investida tira 2 corações. | 2 carnes de cervo, 1 couro, 8 XP |
| Cobra | 6 | No deserto, anuncia o bote e oferece uma abertura durante a recuperação. | 1 carne de cobra, 5 XP |
| Tatu | 6 | Evita o jogador. Quando sobrevive a um golpe, enrola-se por 3 segundos. Golpeá-lo fechado consome energia e o casco o protege. | 1 carne, 1 couro, 5 XP |
| Esqueleto arqueiro | 8 | Surge à noite no exterior. Dispara flechas que percorrem o espaço até o impacto ou fim do alcance. | 5 XP, sem item |
| Aranha gigante | 10 | Caçadora noturna da floresta. Avisa a mordida e o salto. O salto pode tirar 2 corações. | 1 ou 2 fios de teia, chance de 1/3 de uma glândula de veneno, 8 XP |
| Tubarão | Imune a golpes | Persegue o nadador e anuncia a investida. Três mordidas desencadeiam o arrasto e o retorno à base. | Sem derrota por combate ou espólio |
| Sandworm | 12 | Minichefe territorial em tocas fixas do deserto. O movimento na areia o faz emergir. Ficar parado permite que volte ao subsolo. A toca vencida permanece vencida. | 1 casco, 5 XP |
| Monstro da mina | 16 | Dorme ao lado do veio. A proximidade ou um golpe no veio o desperta. Morde de perto e investe à distância. Esquivar-se da investida abre uma janela para atacar. | **2 unidades do mineral do veio protegido**, 8 XP |
| Guardião de Pedra | 40 | Dorme na arena da segunda ilha. Alterna soco, salto com onda e arremesso. Sofre dano quando o punho fica preso e após aterrissar. | 3 quartzos, 4 cobres, 40 XP, +1 coração máximo e vida restaurada |

**Guardião de Pedra.** O círculo de oito menires identifica a arena. O soco, a queda do salto e a pedra arremessada podem tirar 2 corações. A onda de choque tira 1 e o jogador pode saltá-la. Ao chegar a 20 de vida ou menos, começa a segunda fase. Os avisos e períodos de vulnerabilidade encurtam, o arremesso lança três pedras e o salto cria duas ondas. Ao se afastar, o jogador permite que o chefe volte ao centro e durma com a vida restante. A derrota fica registrada na ilha e abre o painel de fim da jornada. A exploração pode continuar. [Lógica do Guardião](../src/spawnbound/domain/boss.py)

### Recursos

Árvores, troncos, rochas, veios, arbustos, cactos e cogumelos usam `WorldObject`. O tipo e a variante identificam o recurso. A resistência pertence ao objeto e a energia gasta pertence ao jogador. Um veio de cobre, por exemplo, é uma rocha cuja variante determina tanto a recompensa quanto a picareta necessária.

Resistência mede o trabalho necessário para concluir a coleta. Energia é o **custo total** de esgotar um recurso intacto. Uma ferramenta mais forte reduz o número de golpes. A cobrança acompanha a fração de trabalho realizada, inclusive se o jogador trocar de ferramenta no meio da ação.

| Objeto ou variante | Resistência / energia | Rendimento por coleta | XP | O que muda na célula |
|---|---:|---|---:|---|
| Árvore, inclusive palmeira | 31 / 8 | 2 madeiras | 8 | A árvore tomba e deixa a célula livre. Há pinheiros, copas largas, variantes de outono e três tamanhos de palmeira. |
| Tronco caído | 40 / 24 | 3 madeiras | 18 | Bloqueia a passagem até o último golpe. |
| Rocha comum ou arenito comum | 25 / 10 | 1 pedra | 12 | A picareta abre espaço onde a rocha bloqueava o caminho. |
| Carvão, inclusive arenito com carvão | 25 / 10 | 1 carvão | 15 | Há fontes na mina e no deserto. Alimenta a construção da fogueira e a fundição. |
| Veio de cobre | 25 / 10 | 1 cobre | 20 | A coleta exige pelo menos a picareta de pedra. O cobre participa da progressão de ferramentas e da fundição. |
| Veio de quartzo | 25 / 10 | 1 quartzo | 30 | Requer picareta de cobre ou quartzo. Com a mochila cheia, o golpe final preserva o veio. |
| Cacto | 6 / 6 | 1 cacto | 6 | Recurso sólido do deserto, removido ao esgotar. |
| Arbusto de frutas | 1 / 0 | 1 fruta | 4 | O arbusto conserva posição e cor, fica sem frutos e recusa nova coleta. Os frutos permanecem esgotados. |
| Cogumelos branco, pardo e morchella | 1 / 0 | 2 ou 3 dos comuns, 1 morchella | 3 | A quantidade dos comuns acompanha o grupo desenhado na célula. A coleta remove o grupo. |

O desgaste aparece em estágios e os impactos produzem lascas ou tremor. No último golpe, a sessão verifica se a recompensa cabe no inventário antes de remover o recurso. A imagem do material voando até o jogador comunica uma transferência que o jogo já efetuou. [Especificações, variantes e rendimentos](../src/spawnbound/domain/model.py) · [Coleta e energia](../src/spawnbound/domain/session.py)

**Objeto `Ore` no planejamento.** Na implementação, um veio de cobre tem tipo `ROCK` e variante `copper_ore`. Começa com 25 de resistência. A picareta de madeira não atravessa o veio. A de pedra retira 4 de resistência por golpe e completa a extração em 7 golpes. Na quebra, a célula fica livre e o jogador recebe 1 cobre e 20 XP.

**Drop coletável.** O conceito de `Drop` do planejamento corresponde, na entrega, à transferência do material para o inventário e ao efeito visual de coleta. A recompensa pode depender de uma instância específica. O monstro da mina guarda o tipo de minério do seu veio e concede duas unidades desse material ao ser derrotado.

**Cultivos.** Cada planta é um `Crop` associado a uma célula de solo preparado. Guarda a espécie e o instante do plantio. O tempo determina quatro estágios de crescimento. Na ilha principal, a horta abandonada dá as primeiras colheitas. A planta madura rende 2 XP por colheita e só é retirada se houver espaço na mochila. A composteira devolve sementes ao ciclo.

| Planta | Ciclos completos até amadurecer | Colheita por célula | Utilização |
|---|---:|---:|---|
| Cenoura | 2 | 2 cenouras | Cada unidade devolve 10 de energia ou produz 1 semente na composteira. |
| Nabo | 3 | 2 nabos | Cada unidade devolve 8 de energia ou produz 1 semente. |
| Abóbora | 5 | 1 abóbora | Devolve 18 de energia ou produz 1 semente. |

### Estruturas e construções

A bancada fabrica um item que o jogador pode colocar no mundo. O cais e o moinho já nascem na ilha em ruínas e recebem um reparo. Essas são as duas formas que a construção assume na campanha.

| Objeto | Obtenção ou ativação | Uso e resultado |
|---|---|---|
| Bancada | A mochila oferece fabricação imediata. Uma bancada colocável custa 6 madeiras e 2 pedras. | Ambas abrem as receitas de móveis, estações, vara, kit de ponte e melhorias. A bancada colocada pode ser girada e recolhida. |
| Baú | 5 madeiras | Cada baú possui 32 posições. Permite depositar e retirar pilhas. Ao recolher o móvel, a mochila recebe também seu conteúdo se houver espaço para tudo. |
| Fornalha | 8 pedras e 2 madeiras | 6 cobres e 3 carvões produzem 1 barra de cobre em 3 segundos. Aguarda a retirada do produto. A barra encerra essa cadeia na campanha atual. |
| Composteira | 4 madeiras e 2 frutas | Converte uma cenoura, um nabo ou uma abóbora em uma semente da mesma espécie, em 1,5 s. Fecha o ciclo entre colher e replantar. |
| Fogueira | 3 carvões e 5 pedras | Ilumina, assa e permite passar a noite. Comporta até 4 tipos de produto por vez. A fila processa os lotes sucessivamente. Cancelar devolve os insumos ainda não processados. |
| Cama | 6 madeiras e 1 couro | De dia, recupera até 15 de energia. À tarde ou à noite, dormir avança até a manhã e acrescenta até 50 de energia e 2 corações, respeitando os máximos. A fogueira também oferece o sono até a manhã. |
| Tocha | 2 madeiras | Fonte de luz colocável. A lanterna que acompanha o personagem e as tochas com setas da mina cumprem funções distintas da tocha fabricada. |
| Moinho | Ruína fixa na ilha principal. Reparo de 10 madeiras e 5 pedras. | O painel confere os materiais. A variante restaurada exibe as pás em movimento. O moinho não processa grãos nem é requisito para navegar. |
| Cais e barco | 15 madeiras e 5 pedras no cais em ruínas | O reparo libera a carta náutica. Escolher a ilha inicia a travessia e posiciona o jogador perto do cais de destino. A navegação livre por direção ficou como proposta. |
| Pedra de viagem | A pedra da ilha principal inicia ativa. E ativa outra ao alcance. | E novamente percorre os pontos ativos em sequência. Uma pedra isolada informa que é preciso descobrir outra. A chegada exige uma célula vizinha livre. |
| Casa | Portal da clareira, interior já disponível | Serve de base para distribuir móveis, armazenar itens e descansar. A construção da casa por etapas, sua resistência estrutural e níveis de melhoria ficaram fora da entrega. |
| Kit de ponte | 3 madeiras e 2 pedras na bancada | No mapa de protótipo, usar o kit no vão converte as células em piso de ponte e permite atravessar. A receita permanece no catálogo da campanha, cujo trajeto entre ilhas é marítimo. |

**Objeto `Storage` no planejamento.** O baú colocado recebe o tipo `CHEST` e possui seu próprio `Inventory` no atributo `storage`. Abrir o baú mostra esse inventário ao lado da mochila. Depositar uma pilha altera o conteúdo daquele baú. Outro baú da casa mantém seus próprios itens.

**Instalação e recolhimento.** O móvel precisa estar equipado. A célula deve ser alcançável e livre, inclusive de planta, portal ou ponto reservado. Cama, baú, bancada, composteira e fornalha aceitam orientação. Ao segurar o clique por 0,8 s para recolher, o jogo tenta devolver o móvel, os produtos prontos, o conteúdo armazenado e os ingredientes de lotes pendentes. Se o conjunto exceder a capacidade da mochila, o móvel permanece no lugar. [Receitas e filas](../src/spawnbound/domain/crafting.py)

**Limite da fornalha.** O código também contém receitas para ferro, ouro, tijolo, vidro, frasco e pote. Ferro, ouro, argila e areia como itens extraíveis não aparecem na cadeia de coleta final. O chão arenoso e as rochas de arenito do deserto não fornecem o item de areia da receita. O jogador consegue produzir a barra de cobre com recursos efetivamente encontrados. [Catálogo da fornalha](../src/spawnbound/domain/crafting.py) · [Itens extraíveis](../src/spawnbound/domain/model.py)

### Elementos do mundo

| Elemento | Estado ou condição | Ação no cenário |
|---|---|---|
| Obstáculo (`Blocker` no planejamento) | Árvore ou tronco de pé, rocha intacta, parede da mina | A célula bloqueia o caminho. Cortar, quebrar ou escavar pode abrir passagem. O limite externo da mina permanece protegido. |
| Água, margem e desnível | Água rasa ou profunda, terra em alturas diferentes | A água rasa permite nadar. A faixa profunda limita o deslocamento. Um passo normal vence até um nível de altura. |
| Entrada da casa ou da mina · `Portal` | Jogador ao alcance do acesso | A interação resolve o espaço de destino e a posição de chegada. Ao voltar, o jogador encontra o estado anterior dos objetos. |
| Menir · `MENHIR` | Oito pedras fixas na arena | As pedras marcam o círculo em torno do Guardião adormecido. Aproximar-se do chefe inicia o encontro. |
| Perigo (`Hazard` no planejamento) | Nadador perto do tubarão, arqueiro ativo à noite, golpe do chefe em curso | O risco depende do animal, do projétil ou da área do golpe. Cada encontro define como o jogador pode escapar. |
| Vida ambiente | Varia com o lugar, a hora e a aproximação | Borboletas, abelhas, sapos e vaga-lumes ocupam o cenário. O sapo mergulha quando o jogador chega perto. Os refúgios dos cardumes também influenciam a pesca. |

### Elementos de eventos

| Evento e representação | Como começa | Efeito e término |
|---|---|---|
| Golpe do jogador · ação da sessão | Selecionar um recurso ou atacar uma criatura ao alcance | Consome a energia correspondente e aplica o efeito do equipamento. O ataque resolve o dano e a coleta avança o desgaste. |
| Flecha · `Arrow` | Um esqueleto arqueiro conclui a mira | Percorre o segmento entre origem e destino. Atingir o jogador ou completar o trajeto encerra o projétil. |
| Onda e pedra do Guardião · `Ring` e `Rock` | Aterrissagem do salto ou arremesso | A onda se expande e permite esquiva por salto. A sombra antecipa o local de impacto da pedra. |
| Despertar de criatura | Aproximar-se da arena ou do veio guardado, ou atingir o alvo | O Guardião entra em combate. Na mina, golpear o veio também desperta seu guardião. |
| Descoberta e objetivo · `IslandSurvey` e `Objective` | Explorar novas células ou satisfazer a condição do objetivo | Revela o mapa ou registra uma etapa da campanha. A sessão conserva os marcos já alcançados. |

### Diagrama de classes simplificado

O esquema mostra onde ficam os dados durante a partida. Os ramos indicam composição ou associação entre as estruturas.

```text
GameSession
├── Player ── Inventory
├── WorldSpaces ── World (ilha, mina ou abrigo)
│                  ├── TileMap ── Tile
│                  ├── WorldObject ── ObjectSpec
│                  │   ├── Inventory (baú)
│                  │   └── Production (estações)
│                  ├── Portal
│                  └── Crop (por célula plantada)
└── Wildlife ── Mob
                └── Guardian (estado especial do chefe)
```

## Atributos

Os dados fixos descrevem o que um tipo de objeto pode fazer. Os dados da instância registram o que já aconteceu com aquele exemplar. Duas rochas de cobre usam a mesma regra de extração e podem ter resistências restantes diferentes.

| Representação | Atributos principais | Uso na partida |
|---|---|---|
| `WorldObject` | `object_id`, `position`, `elevation`, `kind`, `variant`, `durability`, `available` | Identificam qual objeto ocupa a célula, quanto desgaste sofreu e se ainda pode ser usado. |
| `ObjectSpec` | `durability`, `total_energy`, `xp_reward`, `drops`, `blocks_movement` | Definem a resistência inicial, o custo total da extração, a recompensa básica e o bloqueio de passagem. |
| `Player` | `position`, `facing`, `hearts`, `energy`, `xp`, `level`, `inventory` | Relacionam alcance, equipamento, sobrevivência e progressão. |
| `Mob` | `kind`, `hp`, `home`, `windup`, `loot` | Distinguem espécie, vida, território, preparação do golpe e recompensa individual. |
| `Production` | `recipe`, `pending`, `ready`, `next_finish`, `queue`, `stock` | Uma estação mantém seu próprio lote, o instante de conclusão e a saída disponível para retirada. |
| `Crop` | `kind`, `planted` | A espécie e o tempo decorrido determinam quando a célula pode ser colhida. |

### Catálogos de objetos, ferramentas e alimentos

| Família | Identificadores em `ObjectKind` |
|---|---|
| Recursos | `TREE`, `FALLEN_LOG`, `ROCK`, `BERRY_BUSH`, `MUSHROOM`, `CACTUS` |
| Móveis, estações e iluminação | `BED`, `CHEST`, `BENCH`, `KILN`, `COMPOSTER`, `CAMPFIRE`, `TORCH` |
| Estruturas e marcos | `WINDMILL`, `DOCK`, `WAYSTONE`, `MENHIR` |

| Ferramenta | Ação e evolução de madeira → pedra → cobre → quartzo |
|---|---|
| Machado | Retira 3, 4, 6 ou 8 pontos de resistência por golpe em árvores e troncos. Com outro item ou com a mão, retira 1. |
| Picareta | Aplica as mesmas forças a rochas. Madeira já extrai pedra e carvão. O veio de cobre exige pedra ou melhor. O de quartzo exige cobre ou melhor. |
| Espada | Causa 2, 3, 4 ou 5 de dano à criatura. Um ataque comum custa 5 de energia. Há regras específicas para o casco fechado do tatu, a armadura do Guardião e o tubarão. |
| Foice | A de madeira prepara a terra em duas passadas. A partir de pedra, uma passada basta. A semente só pode ser plantada depois do preparo completo. |
| Vara de pesca | A bancada combina 1 madeira e 3 fios de teia. A vara habilita lançamento, fisgada e captura. Ela fica fora da sequência de quatro melhorias. |

Para melhorar uma das quatro ferramentas, a primeira etapa consome 2 madeiras e 3 pedras, a segunda 2 pedras e 1 cobre, a terceira 1 quartzo e 2 madeiras. A melhoria substitui a ferramenta anterior. A tecla U atua sobre a selecionada e a bancada também oferece as receitas. [Ferramentas e custos](../src/spawnbound/domain/tools.py)

**Comida e cura.** A fruta devolve 10 de energia, o cogumelo branco 6 e o pardo 8. A **morchella** devolve **20 de energia e 1 coração**. Carne comum, carne de cervo e carne de cobra assadas devolvem, respectivamente, 32, 45 e 26 de energia, além de 1 coração. Peixe cru devolve 6 de energia e tira 1 coração. Assado, recupera 1 coração e energia conforme a dificuldade da espécie. O jogo recusa o alimento cru que custaria o último coração. [Efeitos dos alimentos](../src/spawnbound/domain/session.py)

## Elementos e sistemas que não precisam ser Game Objects

O inventário armazena recursos por tipo e quantidade. A receita define ingredientes e produto. A interface consulta esses dados quando o jogador abre a mochila ou escolhe algo para fabricar. Assim, uma madeira pode passar da coleta à receita de um baú sem ocupar uma célula própria no chão.

| Sistema auxiliar do planejamento | Resultado na versão final |
|---|---|
| Inventário e barra rápida (`Inventory`, `Hotbar`, `InventoryUI`) | Mochila e barra usam o mesmo inventário. Selecionar um espaço define o equipamento. A interface permite mover pilhas, trocar com a barra e transferir unidades. O baú usa um segundo inventário. |
| HUD e mensagens de ação (`HUD`, `show_message`) | Exibem corações, energia, progresso de nível, objetivo atual e avisos. O chefe tem barra própria. O indicador de temperatura é visual e ainda não modifica sobrevivência ou dano. |
| Fabricação e interação (`CraftingMenu`, `InteractionPrompt`) | A bancada mostra materiais e melhorias. As estações exibem lote e saída. Os reparos do cais e do moinho mostram quantidades disponíveis e exigidas. Um aviso explica recusas por alcance, energia, materiais ou falta de espaço. |
| Mapa da ilha (`Minimap` no plano) | O mapa aberto com M mostra a área revelada. Cada ilha tem seu registro de descoberta. A carta náutica do cais é outra interface e serve para selecionar o destino da viagem. |
| Menu de pausa e saves (`PauseMenu`) | Três espaços de salvamento guardam a sessão. O carregamento recompõe jogador, mundos visitados e progresso. O jogo impede salvar no meio de uma travessia. O avanço do guia e as dicas já vistas também são preservados. |

**Capacidade.** O jogador tem 5 posições na barra rápida e 15 na mochila. Itens comuns formam pilhas de até 64. Cada ferramenta ocupa uma posição. O baú acrescenta um inventário independente de 32 posições.

### Pesca

A vara equipada inicia o lançamento. A boia pode atingir uma célula de água a até 6 células do jogador. Perto de um refúgio de cardume, a espera cai para 55% da duração sorteada. Após o sinal da mordida, o jogador tem 0,9 s para fisgar. No minigame, precisa manter o peixe dentro da barra até encher o medidor. Se a mochila estiver cheia, o peixe volta à água.

A espécie capturada depende da água, do período e de um sorteio ponderado. Cada espécie tem sua dificuldade e seu padrão de nado. O bagre tende a afundar, o baiacu tende a flutuar e a traíra muda de posição em arrancadas.

| Habitat | Disponíveis nos dois períodos | Seleção diurna | Seleção noturna |
|---|---|---|---|
| Rio e lago | Lambari, traíra, pirarucu | Tilápia, tucunaré | Bagre |
| Mar | Sardinha, baiacu, garoupa | Tainha, atum | Robalo |

## Arquitetura de arquivos

| Parte do projeto | Onde encontrar as regras da versão final |
|---|---|
| Mundo e território | [Modelo de células e objetos](../src/spawnbound/domain/model.py) · [Geração das ilhas](../src/spawnbound/domain/generation.py) · [Espaços e portais](../src/spawnbound/domain/spaces.py) · [Arquipélago e cais](../src/spawnbound/domain/archipelago.py) |
| Personagens, ataques e eventos | [Sessão e ações do protagonista](../src/spawnbound/domain/session.py) · [Fauna e projéteis](../src/spawnbound/domain/mobs.py) · [Guardião de Pedra](../src/spawnbound/domain/boss.py) |
| Recursos e produção | [Inventário](../src/spawnbound/domain/inventory.py) · [Ferramentas](../src/spawnbound/domain/tools.py) · [Receitas e lotes](../src/spawnbound/domain/crafting.py) · [Cultivos](../src/spawnbound/domain/farming.py) |
| Pesca, descoberta e progresso | [Espécies de peixes](../src/spawnbound/domain/fish.py) · [Pesca](../src/spawnbound/domain/fishing.py) · [Exploração](../src/spawnbound/domain/exploration.py) · [Objetivos](../src/spawnbound/domain/guide.py) |
| Interface e persistência | [Interface do inventário](../src/spawnbound/inventory_hud.py) · [Mapa da ilha](../src/spawnbound/island_map.py) · [Salvamento](../src/spawnbound/savegame.py) |

## Escopo inicial e expansão futura

| Ideia do catálogo original | Destino na versão final |
|---|---|
| Agricultura e minimapa como expansões | A campanha inclui a horta, o ciclo de sementes e um mapa por ilha que revela o terreno explorado. |
| Ponte e plataformas entre setores | A ponte construível funciona no mapa de protótipo. Na campanha, o cais reparado leva à segunda ilha e as pedras ativadas permitem a viagem de volta. |
| Sobreviventes, tarefas, habilidades e trocas | Os personagens `NPC`, as missões `Quest` e a árvore de habilidades permaneceram propostas. O guia acompanha a progressão por materiais, estruturas e exploração. |
| Um chefe por região e novas áreas | A entrega tem duas ilhas, floresta, campina e deserto. Cada ilha tem uma mina e a segunda tem o Guardião de Pedra. Tundra, taiga e andares desbloqueáveis na mina ficaram para expansão. |
| Recompensas especiais e novas receitas | A aranha fornece teia para a vara. A glândula de veneno, o casco do sandworm e a barra de cobre podem ser obtidos. Seu uso em receitas posteriores ficou em aberto. |

As decisões sobre rega, travessia livre de barco, sobreviventes e outros recortes estão reunidas no [Game Design Document](GDD-SpawnBound.md).
