"""Small certificate templates used by the tests."""

SVG = '''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     width="297mm" height="210mm" viewBox="0 0 297 210">
  <text x="20" y="40" font-size="10">Certificate for $name</text>
  <text x="20" y="60" font-size="8" data-institute="$institute">from $institute</text>
  <image x="20" y="150" width="40" height="40" xlink:href="qrcode.png"/>
  <text x="20" y="200" font-size="6">Serial: $serial_key</text>
</svg>
'''

TEX = r'''\documentclass[a4paper,landscape]{article}
\usepackage{qrcode}
\pagestyle{empty}
\begin{document}
Certificate for $name from $institute

\qrcode{$qr_code}

Serial: $serial_key
\end{document}
'''
