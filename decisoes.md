# PPlay, pygame e Python no SpawnBound

O *Power PPlay 2.0* é o framework da disciplina e já usa *pygame-ce* por baixo. Nossa primeira escolha foi aproveitar o que o PPlay oferecia. Quando precisamos montar imagens de um jeito específico, chamamos o pygame diretamente. Para definir as regras da ilha, escrevemos código nosso em Python. Dá para ver os três trabalhando juntos quando o jogador clica numa árvore.

## Como dividimos o trabalho no jogo

O PPlay está presente do menu ao combate, ele atualiza a janela, lê o teclado e o mouse, troca as cenas, exibe o personagem e as criaturas, fornece os botões e as barras da interface e toca a música e os efeitos. Usamos *13 módulos e 17 classes* do framework. Por exemplo, o módulo de som atende tanto ao menu quanto à ilha, à mina e à luta com o chefe, embora a integração esteja concentrada em um único arquivo nosso.

Boa parte do uso direto de pygame vem da arte. Dos *41 arquivos* que importam pygame, *39* têm pelo menos uma chamada para criar uma imagem em memória (⁠ Surface ⁠), desenhar formas ou transformar imagens. Isso inclui sprites, terreno e interface. Só entre os arquivos com o nome terminado em ⁠ _art.py ⁠, há *19* que importam pygame. A pedra com veios de cobre, a chama da fogueira e o barco no cais, por exemplo, têm rotinas de desenho próprias.

O *cervo* mostra como as duas bibliotecas trabalham juntas. Para montar uma pose, nosso código escolhe as cores, coloca os pixels numa imagem do pygame e guarda o resultado para reutilizar. Para mostrar o cervo na ilha, entregamos essa imagem ao ⁠ GameImage.draw() ⁠ do PPlay. O método recebe uma figura pronta para exibir. A limitação de desempenho apareceu em outra situação, ao repetir o desenho para milhares de peças paradas do terreno, por isso para o desenho da ilha, que envolve milhares de blocos, utilizamos outro método.

Em Python ficam as regras que criamos. Na luta com o mesmo cervo, nosso código decide quando ele dá um coice, até onde alcança e quanto dano causa. Dos *88 arquivos* de ⁠ src/spawnbound ⁠, *40* dependem apenas de código do projeto e da biblioteca padrão do Python, incluindo os 25 do núcleo de regras. [Comportamento das criaturas](src/spawnbound/domain/mobs.py) · [Regras da partida](src/spawnbound/domain/session.py)

A contagem considera o código do jogo, excluindo dependências, testes e ferramentas. Seis arquivos importam PPlay diretamente e outros 19 importam algum desses seis. Contar arquivos ajuda a localizar o código. Como o exemplo do cervo mostra, um mesmo arquivo pode usar as duas bibliotecas em etapas diferentes.

## Por que algumas partes ficaram fora do PPlay?

*1. Desenho da ilha*
Dava para desenhar árvores e pedras com ⁠ GameImage.draw() ⁠. O problema era repetir o trabalho para milhares de peças enquanto a câmera andava. O método do PPlay copia a imagem a cada desenho, e o mapa que vem com ele organiza sprites em uma grade plana. Para o nosso terreno isométrico, criamos com pygame um cache, ou seja, guardamos na memória pedaços do cenário já desenhados. Quando a câmera anda, reaproveitamos esses pedaços. Quando uma árvore cai, refazemos a região afetada. 

*2. Caminho por clique*
O PPlay já tem uma busca de caminhos. Ela testa quatro vizinhos de cada célula e verifica se a passagem está bloqueada. No SpawnBound podemos andar na diagonal, subir um degrau e entrar na água por uma margem baixa. Por isso escrevemos a busca em Python. Se o jogador clicar do outro lado de um barranco, ela procura por onde dá para subir e leva em conta a altura de cada passo. O clique que inicia esse percurso continua vindo do mouse do PPlay.

*3. Tempo dos quadros*
O relógio da janela do PPlay mede o intervalo entre quadros em milissegundos inteiros. Uma tela de 60 Hz, por exemplo, se atualiza a cada 16,67 ms. Para a câmera andar num ritmo regular, usamos ⁠ time.perf_counter() ⁠ do Python para medir frações de milissegundo e ajustar quando apresentar cada quadro. A janela continua sendo atualizada pelo PPlay, e as transições das dicas usam o tempo dele.

*4. Lanterna e interface*
O PPlay oferece luzes circulares, botões e barras. Na mina, queríamos uma área de luz achatada pela perspectiva, que clareasse a textura da pedra perto da lanterna. Usamos pygame para desenhar essa área e misturá-la com o cenário. Nos menus, aproveitamos a classe de botão do PPlay e usamos pygame só para personalizar seu desenho, incluindo a borda e a fonte de pixels. A razão aqui foi a aparência que escolhemos.

*5. Regras da partida*
Ao cortar uma árvore, o PPlay informa que o botão está pressionado, desenha a animação e toca o som. Quem decide quanto o machado tira da resistência da árvore, quanta energia o jogador gasta e quando a madeira entra na mochila é o nosso código em Python. Escolhemos escrever essas regras separadas da janela para conseguir testá-las sem abrir o jogo. O mesmo vale para gerar uma ilha pela seed e definir quando o peixe foi capturado. Nesse caso, a justificativa é poder criar e testar as regras específicas do SpawnBound.