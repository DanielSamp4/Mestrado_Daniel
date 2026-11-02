# Leitor de notas fiscais

## Captura

Instale as dependencias Python e o aplicativo Tesseract OCR (com o idioma `por`) no Windows:

```powershell
pip install -r requirements.txt
python main.py
```

Comece pelo topo da nota. Quando um trecho for salvo, mova a nota **para cima**, mantendo aproximadamente 25% do trecho anterior visivel. Cada salvamento automatico abre/atualiza a janela `Ultimo trecho capturado (automatico)` com o frame bruto que foi gravado. Pressione `f` para finalizar e manter a sessao; `q` cancela. Se o salvamento automatico nao ocorrer, pressione `s` para salvar manualmente quando a janela indicar que ha texto detectado.

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
