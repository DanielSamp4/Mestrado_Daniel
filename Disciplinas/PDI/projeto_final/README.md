# Leitor de notas fiscais

## Captura

Instale as dependencias Python e o aplicativo Tesseract OCR (com o idioma `por`) no Windows:

```powershell
pip install -r requirements.txt
python main.py
```

Comece pelo topo da nota. Quando um trecho for salvo, mova a nota **para cima**, mantendo aproximadamente 25% do trecho anterior visivel. Cada salvamento automatico abre/atualiza a janela `Ultimo trecho capturado (automatico)` com o frame bruto que foi gravado. Pressione `f` para finalizar e manter a sessao; `q` encerra e processa as fotos. Se o salvamento automatico nao ocorrer, pressione `s` para salvar manualmente quando a janela indicar que ha texto detectado.

Os trechos ficam em `captures/nota_AAAAMMDD_HHMMSS/`, na ordem de leitura.

## OCR e registro

O comando gera `analise_itens.csv` (para Excel) e `analise_itens.md` (tabela legivel) dentro da pasta da sessao. Revise-os antes de persistir:

```powershell
python scan_receipt.py captures/nota_AAAAMMDD_HHMMSS
```

Quando os campos e itens estiverem corretos, salve-os no banco local SQLite:

```powershell
python scan_receipt.py captures/nota_AAAAMMDD_HHMMSS --save
```

O arquivo `purchases.sqlite3` guarda a compra, os itens, os precos e o texto bruto reconhecido. OCR pode errar caracteres e valores; a proxima evolucao recomendada e uma tela de revisao/edicao antes do `--save`.


## Escolha do metodo

Ao executar `python main.py`, escolha `1` (scanning) ou `2` (QR Code).
Scanning mantem a captura e o OCR existentes. QR Code abre a camera e consulta
os dados digitais assim que identifica o codigo; `q` ou fechar a janela encerra.
A importacao digital suporta a consulta NFC-e de Pernambuco, que retorna XML.
Falhas de rede ou respostas sem os dados da nota sao informadas no terminal.

As importacoes ficam em `captures/qrcode_.../`: `analise_itens.csv`,
`itens_digitais.csv` (com numero, codigo e desconto por item), `nota.xml` e
`origem.txt`. Produtos repetidos em linhas distintas sao preservados.
O valor bruto dos produtos pode diferir do total da nota por descontos e acrescimos.
A contagem digital corresponde aos elementos de item do XML; nao e uma validacao
independente. Os pares semelhantes do relatorio compartilhado nao implicam erro
na nota digital.

## Dashboard local

Execute `python dashboard.py` e acesse http://127.0.0.1:8765.
O painel carrega os CSVs em captures, com preferencia pelo CSV digital dentro
 de cada sessao. Escolha uma nota por vez; use Atualizar notas apos novas capturas.
Mostra peso alimentar, custo ponderado por kg, doces/salgados e calorias estimadas.
Categorias e kcal/100 g sao hipoteses editaveis, nao valores do fabricante.
Peso em UN so e inferido quando a descricao informa G ou KG. Litros e pesos
 desconhecidos nao entram no custo/kg. Edite peso total, grupo, sabor e kcal/100 g
na tabela; ajustes persistem no navegador e podem ser exportados em CSV.
Proteinas/carboidratos sao grupos de alimentos, nao gramas de macronutrientes.
O servidor atende apenas em 127.0.0.1 e nao exige dependencias adicionais.
