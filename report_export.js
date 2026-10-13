/* 위탁운용 분석보고서 내보내기: A4 맞춤형 PDF 및 Word(.docx) 다운로드 */

// 1. PDF 내보내기 (html2pdf 기반, A4 780px 너비 맞춤으로 가로 잘림 0%, 블록 절단 방지)
function exportPdf() {
  const b = document.getElementById('btnPdf');
  if (!b) return;
  b.disabled = true;
  b.textContent = '⏳ PDF 생성 중...';
  
  // PDF용 A4 너비 모드 활성화
  document.body.classList.add('pdf-mode');
  
  // 차트들을 780px 너비에 맞게 리사이징
  if (window.Chart && Chart.instances) {
    Object.values(Chart.instances).forEach(c => c.resize());
  }

  setTimeout(() => {
    const el = document.querySelector('.wrap');
    const fname = window.REPORT_FNAME || '위탁운용_분석보고서';
    
    const opt = {
      margin: [10, 6, 10, 6],
      filename: fname + '.pdf',
      image: { type: 'jpeg', quality: 0.98 },
      html2canvas: {
        scale: 2,
        useCORS: true,
        backgroundColor: '#ffffff',
        windowWidth: 800,
        width: 780,
        scrollY: 0
      },
      jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
      pagebreak: {
        mode: ['css', 'legacy'],
        avoid: ['tr', '.fund', '.chart', '.kpi', 'h2', 'h3', '.need', '.note', '.mgr h3']
      }
    };

    html2pdf().set(opt).from(el).save()
      .catch(err => {
        console.error('PDF export error:', err);
        alert('PDF 생성 중 오류가 발생했습니다: ' + err);
      })
      .finally(() => {
        document.body.classList.remove('pdf-mode');
        if (window.Chart && Chart.instances) {
          Object.values(Chart.instances).forEach(c => c.resize());
        }
        b.disabled = false;
        b.textContent = '📄 PDF 저장';
      });
  }, 400);
}

// 2. 한글/워드 문서 내보내기 (표 + 4개 차트 고해상도 이미지 포함 정식 .docx)
function exportDocx() {
  if (!window.JSZip) {
    alert('Word 라이브러리를 불러오지 못했습니다. 인터넷 연결을 확인해 주세요.');
    return;
  }
  const b = document.getElementById('btnHwp');
  if (b) {
    b.disabled = true;
    b.textContent = '⏳ 문서 생성 중...';
  }

  try {
    const zip = new JSZip();
    const XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';
    const clean = t => (t || '').replace(/\s+/g, ' ').trim();
    const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    const FONT = '<w:rFonts w:ascii="맑은 고딕" w:hAnsi="맑은 고딕" w:eastAsia="맑은 고딕" w:cs="맑은 고딕"/>';
    const TXT_W = 10206; // A4 폭 (dxa 단위)

    const run = (text, o) => {
      o = o || {};
      return '<w:r><w:rPr>' + FONT + (o.b ? '<w:b/>' : '') + (o.color ? '<w:color w:val="' + o.color + '"/>' : '') +
        '<w:sz w:val="' + (o.sz || 20) + '"/><w:szCs w:val="' + (o.sz || 20) + '"/></w:rPr><w:t xml:space="preserve">' + esc(text) + '</w:t></w:r>';
    };

    const para = (text, o) => {
      o = o || {};
      return '<w:p><w:pPr>' + (o.keep ? '<w:keepNext/>' : '') + (o.pb ? '<w:pageBreakBefore/>' : '') +
        '<w:spacing w:before="' + (o.before || 0) + '" w:after="' + (o.after == null ? 60 : o.after) + '"/><w:jc w:val="' + (o.al || 'left') + '"/>' +
        (o.bd ? '<w:pBdr><w:bottom w:val="single" w:sz="8" w:space="2" w:color="4F46E5"/></w:pBdr>' : '') +
        '</w:pPr>' + (text === '' ? '' : run(text, o)) + '</w:p>';
    };

    const images = [];
    const imageXml = (cv) => {
      const n = images.length + 1;
      images.push(cv.toDataURL('image/png').split(',')[1]);
      const cx = 5600000;
      const cy = Math.round(cx * cv.height / cv.width);
      return '<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="' + cx + '" cy="' + cy + '"/>' +
        '<wp:docPr id="' + n + '" name="chart' + n + '"/><a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">' +
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="' + n + '" name="chart' + n + '.png"/><pic:cNvPicPr/></pic:nvPicPr>' +
        '<pic:blipFill><a:blip r:embed="rIdImg' + n + '"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>' +
        '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="' + cx + '" cy="' + cy + '"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>';
    };

    const chartImg = (box) => {
      const cv = box.tagName === 'CANVAS' ? box : box.querySelector('canvas');
      if (!cv || !cv.width) return '';
      const c2 = document.createElement('canvas');
      c2.width = cv.width;
      c2.height = cv.height;
      const g = c2.getContext('2d');
      g.fillStyle = '#ffffff';
      g.fillRect(0, 0, c2.width, c2.height);
      g.drawImage(cv, 0, 0);
      return imageXml(c2);
    };

    const tableXml = (tbl) => {
      const trs = Array.from(tbl.querySelectorAll('tr'));
      const occ = [], start = {};
      let ncols = 0;
      trs.forEach((tr, r) => {
        occ[r] = occ[r] || [];
        let c = 0;
        Array.from(tr.children).forEach(td => {
          while (occ[r][c]) c++;
          const cs = td.colSpan || 1, rs = td.rowSpan || 1;
          for (let i = 0; i < rs; i++) {
            for (let j = 0; j < cs; j++) {
              occ[r + i] = occ[r + i] || [];
              occ[r + i][c + j] = { r0: r, c0: c, cs: cs };
            }
          }
          start[r + ',' + c] = {
            cs: cs, rs: rs, th: td.tagName === 'TH',
            left: td.classList.contains('l'), text: clean(td.innerText),
            pos: td.classList.contains('pos'), neg: td.classList.contains('neg')
          };
          c += cs;
          ncols = Math.max(ncols, c);
        });
      });
      if (!ncols) return '';
      const w0 = ncols > 8 ? 1100 : 1500;
      const first = Math.max(w0, Math.floor(TXT_W * 0.12));
      const rest = Math.floor((TXT_W - first) / Math.max(ncols - 1, 1));
      let grid = '', cw = [];
      for (let k = 0; k < ncols; k++) {
        cw[k] = k === 0 ? first : rest;
        grid += '<w:gridCol w:w="' + cw[k] + '"/>';
      }
      const brd = ['top', 'left', 'bottom', 'right', 'insideH', 'insideV'].map(s => '<w:' + s + ' w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>').join('');
      let out = '<w:tbl><w:tblPr><w:tblW w:w="' + TXT_W + '" w:type="dxa"/><w:tblBorders>' + brd + '</w:tblBorders><w:tblLayout w:type="fixed"/>' +
        '<w:tblCellMar><w:left w:w="60" w:type="dxa"/><w:right w:w="60" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>' + grid + '</w:tblGrid>';
      for (let r = 0; r < trs.length; r++) {
        out += '<w:tr><w:trPr><w:cantSplit/></w:trPr>';
        for (let c = 0; c < ncols; c++) {
          const o = occ[r] && occ[r][c], s = start[r + ',' + c];
          if (s) {
            let w = 0;
            for (let q = 0; q < s.cs; q++) w += cw[c + q];
            out += '<w:tc><w:tcPr><w:tcW w:w="' + w + '" w:type="dxa"/>' + (s.cs > 1 ? '<w:gridSpan w:val="' + s.cs + '"/>' : '') +
              (s.rs > 1 ? '<w:vMerge w:val="restart"/>' : '') + (s.th ? '<w:shd w:val="clear" w:color="auto" w:fill="F1F5F9"/>' : '') + '<w:vAlign w:val="center"/></w:tcPr>' +
              para(s.text, { sz: 16, b: s.th, al: s.left ? 'left' : 'right', after: 0, color: s.pos ? 'DC2626' : s.neg ? '2563EB' : null }) + '</w:tc>';
          } else if (o && o.r0 < r && o.c0 === c) {
            let w2 = 0;
            for (let q2 = 0; q2 < o.cs; q2++) w2 += cw[c + q2];
            out += '<w:tc><w:tcPr><w:tcW w:w="' + w2 + '" w:type="dxa"/>' + (o.cs > 1 ? '<w:gridSpan w:val="' + o.cs + '"/>' : '') + '<w:vMerge/></w:tcPr><w:p/></w:tc>';
          }
        }
        out += '</w:tr>';
      }
      return out + '</w:tbl>' + para('', { after: 80 });
    };

    let out = '', root = document.querySelector('.wrap');
    out += para(clean(root.querySelector('h1').innerText), { sz: 40, b: true, color: '4F46E5', after: 40 });
    const sub = root.querySelector('.sub');
    if (sub) out += para(clean(sub.innerText), { sz: 18, color: '64748B' });
    const badge = root.querySelector('.badge');
    if (badge) out += para(clean(badge.innerText), { sz: 18, color: '64748B', al: 'right' });

    function walk(node) {
      Array.from(node.children).forEach(el => {
        const t = el.tagName, cl = el.classList;
        if (cl.contains('tools') || cl.contains('toc') || t === 'SCRIPT' || t === 'STYLE' || t === 'HEADER') return;
        if (t === 'SECTION') {
          if (['s2', 's4', 's5', 's6'].includes(el.id)) out += '<w:p><w:r><w:br w:type="page"/></w:r></w:p>';
          walk(el);
        } else if (t === 'H2') out += para(clean(el.innerText), { sz: 28, b: true, before: 160, bd: true, keep: true });
        else if (t === 'H3') out += para(clean(el.innerText), { sz: 22, b: true, before: 120, keep: true });
        else if (t === 'TABLE') out += tableXml(el);
        else if (t === 'UL' || t === 'OL') Array.from(el.children).forEach(li => { out += para('· ' + clean(li.innerText), { sz: 19 }); });
        else if (cl.contains('kpis')) Array.from(el.children).forEach(k => {
          out += para('· ' + clean(k.querySelector('.kl').innerText) + ': ' + clean(k.querySelector('.kv').innerText) + ' (' + clean(k.querySelector('.ks').innerText) + ')', { sz: 19 });
        });
        else if (cl.contains('fund')) {
          out += para(clean(el.querySelector('.fh').innerText), { sz: 20, b: true, before: 80, keep: true });
          el.querySelectorAll('li').forEach(li => { out += para('· ' + clean(li.innerText), { sz: 18 }); });
        } else if (cl.contains('chart')) out += chartImg(el);
        else if (cl.contains('grid2')) Array.from(el.children).forEach(c => { out += chartImg(c); });
        else if (cl.contains('note') || cl.contains('need') || t === 'P') out += para(clean(el.innerText), { sz: 17, color: '64748B' });
        else if (t === 'FOOTER') out += para(clean(el.innerText), { sz: 16, color: '64748B', al: 'center', before: 200 });
        else if (t === 'H1') return;
        else if (t === 'DIV' && el.querySelector(':scope > table')) walk(el);
        else if (el.children.length) walk(el);
      });
    }
    walk(root);

    const NSW = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"';
    zip.file('[Content_Types].xml', XML + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>');
    zip.file('_rels/.rels', XML + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>');
    let rels = '<Relationship Id="rIdSty" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>';
    images.forEach((b64, i) => {
      rels += '<Relationship Id="rIdImg' + (i + 1) + '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/chart' + (i + 1) + '.png"/>';
      zip.file('word/media/chart' + (i + 1) + '.png', b64, { base64: true });
    });
    zip.file('word/_rels/document.xml.rels', XML + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + rels + '</Relationships>');
    zip.file('word/styles.xml', XML + '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults><w:rPrDefault><w:rPr>' + FONT + '<w:sz w:val="20"/><w:szCs w:val="20"/><w:lang w:val="ko-KR" w:eastAsia="ko-KR"/></w:rPr></w:rPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style></w:styles>');
    zip.file('word/document.xml', XML + '<w:document ' + NSW + '><w:body>' + out + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1000" w:right="850" w:bottom="1000" w:left="850" w:header="500" w:footer="500" w:gutter="0"/></w:sectPr></w:body></w:document>');

    const fname = window.REPORT_FNAME || '위탁운용_분석보고서';
    zip.generateAsync({ type: 'blob', mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', compression: 'DEFLATE' }).then(blob => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = fname + '.docx';
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1500);
    });
  } catch (e) {
    console.error('Word export error:', e);
    alert('Word/한글 문서 생성 중 오류가 발생했습니다: ' + e);
  } finally {
    if (b) {
      b.disabled = false;
      b.textContent = '📝 한글/워드 저장(.docx)';
    }
  }
}
