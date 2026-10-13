/* 위탁운용 분석보고서 내보내기 (PDF / 한글 HWPX) */
(function () {
  var FNAME = window.REPORT_FNAME || '위탁운용_분석보고서';

  /* ---------------- PDF ---------------- */
  window.exportPdf = function () {
    var b = document.getElementById('btnPdf');
    b.disabled = true; b.textContent = '⏳ 생성 중...';
    var el = document.querySelector('.wrap');
    document.body.classList.add('pdf-mode');
    Object.values(Chart.instances).forEach(function (c) { c.resize(); });
    // 레이아웃 반영 후 캡처
    setTimeout(function () {
      html2pdf().set({
        margin: [10, 8, 12, 8],
        filename: FNAME + '.pdf',
        image: { type: 'jpeg', quality: 0.95 },
        html2canvas: { scale: 2, useCORS: true, backgroundColor: '#ffffff', windowWidth: 900 },
        jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
        pagebreak: {
          mode: ['css', 'legacy'],
          before: ['#s2', '#s4', '#s5', '#s6'],
          avoid: ['tr', '.fund', '.chart', '.kpi', 'h2', 'h3', '.need', '.note', 'li', '.mgr > h3']
        }
      }).from(el).save().finally(function () {
        document.body.classList.remove('pdf-mode');
        Object.values(Chart.instances).forEach(function (c) { c.resize(); });
        b.disabled = false; b.textContent = '📄 PDF 저장';
      });
    }, 400);
  };

  /* ---------------- 한글(HWPX) ---------------- */
  var NS = 'xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" ' +
    'xmlns:hp10="http://www.hancom.co.kr/hwpml/2016/paragraph" xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" ' +
    'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core" xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" ' +
    'xmlns:hhs="http://www.hancom.co.kr/hwpml/2011/history" xmlns:hm="http://www.hancom.co.kr/hwpml/2011/master-page" ' +
    'xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf" xmlns:dc="http://purl.org/dc/elements/1.1/" ' +
    'xmlns:opf="http://www.idpf.org/2007/opf/"';
  var XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';
  var PAGE_W = 42520; // 본문 폭 (A4, 좌우 여백 30mm)

  // charPr: 0 본문, 1 굵게, 2 제목(큰 글씨), 3 소제목, 4 표(작은 글씨), 5 표 머리글(굵게), 6 주석
  var CHARS = [
    [1000, 0], [1000, 1], [2000, 1], [1200, 1], [800, 0], [800, 1], [850, 0]
  ];
  // paraPr: 0 왼쪽, 1 오른쪽, 2 가운데
  var ALIGN = ['LEFT', 'RIGHT', 'CENTER'];

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function clean(t) { return (t || '').replace(/\s+/g, ' ').trim(); }

  function headerXml() {
    var langs = ['HANGUL', 'LATIN', 'HANJA', 'JAPANESE', 'OTHER', 'SYMBOL', 'USER'];
    var ff = langs.map(function (l) {
      return '<hh:fontface lang="' + l + '" fontCnt="1"><hh:font id="0" face="맑은 고딕" type="TTF" isEmbedded="0"/></hh:fontface>';
    }).join('');
    function border(id, type, fill) {
      var s = '<hh:borderFill id="' + id + '" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">' +
        '<hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/>';
      ['left', 'right', 'top', 'bottom'].forEach(function (d) {
        s += '<hh:' + d + 'Border type="' + type + '" width="0.12 mm" color="#94A3B8"/>';
      });
      s += '<hh:diagonal type="NONE" width="0.1 mm" color="#000000"/>';
      if (fill) s += '<hc:fillBrush><hc:winBrush faceColor="' + fill + '" hatchColor="#999999" alpha="0"/></hc:fillBrush>';
      return s + '</hh:borderFill>';
    }
    var bf = border(1, 'NONE') + border(2, 'SOLID') + border(3, 'SOLID', '#F1F5F9');
    var cp = CHARS.map(function (c, i) {
      return '<hh:charPr id="' + i + '" height="' + c[0] + '" textColor="#000000" shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="1">' +
        '<hh:fontRef hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>' +
        '<hh:ratio hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>' +
        '<hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>' +
        '<hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>' +
        '<hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>' +
        (c[1] ? '<hh:bold/>' : '') +
        '<hh:underline type="NONE" shape="SOLID" color="#000000"/><hh:strikeout shape="NONE" color="#000000"/>' +
        '<hh:outline type="NONE"/><hh:shadow type="NONE" color="#B2B2B2" offsetX="10" offsetY="10"/></hh:charPr>';
    }).join('');
    var pp = ALIGN.map(function (a, i) {
      return '<hh:paraPr id="' + i + '" tabPrIDRef="0" condense="0" fontLineHeight="0" snapToGrid="1" suppressLineNumbers="0" checked="0">' +
        '<hh:align horizontal="' + a + '" vertical="BASELINE"/><hh:heading type="NONE" idRef="0" level="0"/>' +
        '<hh:breakSetting breakLatinWord="KEEP_WORD" breakNonLatinWord="KEEP_WORD" widowOrphan="0" keepWithNext="0" keepLines="0" pageBreakBefore="0" lineWrap="BREAK"/>' +
        '<hh:autoSpacing eAsianEng="0" eAsianNum="0"/>' +
        '<hh:margin><hc:intent value="0" unit="HWPUNIT"/><hc:left value="0" unit="HWPUNIT"/><hc:right value="0" unit="HWPUNIT"/><hc:prev value="0" unit="HWPUNIT"/><hc:next value="0" unit="HWPUNIT"/></hh:margin>' +
        '<hh:lineSpacing type="PERCENT" value="150" unit="HWPUNIT"/>' +
        '<hh:border borderFillIDRef="1" offsetLeft="0" offsetRight="0" offsetTop="0" offsetBottom="0" connect="0" ignoreMargin="0"/></hh:paraPr>';
    }).join('');
    return XML + '<hh:head ' + NS + ' version="1.4" secCnt="1"><hh:beginNum page="1" footnote="1" endnote="1" pic="1" tbl="1" equation="1"/>' +
      '<hh:refList><hh:fontfaces itemCnt="7">' + ff + '</hh:fontfaces>' +
      '<hh:borderFills itemCnt="3">' + bf + '</hh:borderFills>' +
      '<hh:charProperties itemCnt="' + CHARS.length + '">' + cp + '</hh:charProperties>' +
      '<hh:tabProperties itemCnt="1"><hh:tabPr id="0" autoTabLeft="0" autoTabRight="0"/></hh:tabProperties>' +
      '<hh:paraProperties itemCnt="' + ALIGN.length + '">' + pp + '</hh:paraProperties>' +
      '<hh:styles itemCnt="1"><hh:style id="0" type="PARA" name="바탕글" engName="Normal" paraPrIDRef="0" charPrIDRef="0" nextStyleIDRef="0" langID="1042" lockForm="0"/></hh:styles>' +
      '</hh:refList><hh:compatibleDocument targetProgram="HWP2018"><hh:layoutCompatibility/></hh:compatibleDocument>' +
      '<hh:docOption><hh:linkinfo path="" pageInherit="0" footnoteInherit="0"/></hh:docOption></hh:head>';
  }

  var pid = 1000;
  function para(text, ch, al) {
    return '<hp:p id="' + (pid++) + '" paraPrIDRef="' + (al || 0) + '" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">' +
      '<hp:run charPrIDRef="' + (ch || 0) + '"><hp:t>' + esc(text) + '</hp:t></hp:run></hp:p>';
  }

  function tableXml(tbl) {
    var trs = Array.prototype.slice.call(tbl.querySelectorAll('tr'));
    var occ = [], cells = [], ncols = 0;
    trs.forEach(function (tr, r) {
      occ[r] = occ[r] || [];
      var c = 0;
      Array.prototype.slice.call(tr.children).forEach(function (td) {
        while (occ[r][c]) c++;
        var cs = td.colSpan || 1, rs = td.rowSpan || 1;
        for (var i = 0; i < rs; i++) for (var j = 0; j < cs; j++) { occ[r + i] = occ[r + i] || []; occ[r + i][c + j] = 1; }
        cells.push({ r: r, c: c, cs: cs, rs: rs, th: td.tagName === 'TH', left: td.classList.contains('l'), text: clean(td.innerText) });
        c += cs;
        ncols = Math.max(ncols, c);
      });
    });
    if (!cells.length) return '';
    var nrows = trs.length;
    var colW = Math.floor(PAGE_W / ncols), rowH = 1400;
    var rowsXml = '';
    for (var r = 0; r < nrows; r++) {
      var tcs = '';
      cells.filter(function (x) { return x.r === r; }).forEach(function (x) {
        var w = colW * x.cs;
        tcs += '<hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="' + (x.th ? 3 : 2) + '">' +
          '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">' +
          para(x.text, x.th ? 5 : 4, x.left ? 0 : 1) + '</hp:subList>' +
          '<hp:cellAddr colAddr="' + x.c + '" rowAddr="' + x.r + '"/><hp:cellSpan colSpan="' + x.cs + '" rowSpan="' + x.rs + '"/>' +
          '<hp:cellSz width="' + w + '" height="' + (rowH * x.rs) + '"/><hp:cellMargin left="141" right="141" top="141" bottom="141"/></hp:tc>';
      });
      rowsXml += '<hp:tr>' + tcs + '</hp:tr>';
    }
    return '<hp:p id="' + (pid++) + '" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><hp:run charPrIDRef="0">' +
      '<hp:tbl id="' + (pid++) + '" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="1" rowCnt="' + nrows + '" colCnt="' + ncols + '" cellSpacing="0" borderFillIDRef="2" noAdjust="0">' +
      '<hp:sz width="' + (colW * ncols) + '" widthRelTo="ABSOLUTE" height="' + (rowH * nrows) + '" heightRelTo="ABSOLUTE" protect="0"/>' +
      '<hp:pos treatAsChar="0" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="COLUMN" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>' +
      '<hp:outMargin left="0" right="0" top="0" bottom="283"/><hp:inMargin left="141" right="141" top="141" bottom="141"/>' +
      rowsXml + '</hp:tbl></hp:run></hp:p>';
  }

  function bodyXml() {
    var out = '';
    var root = document.querySelector('.wrap');
    out += para(clean(root.querySelector('h1').innerText), 2, 0);
    var sub = root.querySelector('.sub'); if (sub) out += para(clean(sub.innerText), 6, 0);
    var badge = root.querySelector('.badge'); if (badge) out += para(clean(badge.innerText), 6, 1);
    out += para('', 0, 0);

    function walk(node) {
      Array.prototype.slice.call(node.children).forEach(function (el) {
        var tag = el.tagName;
        if (el.classList.contains('tools') || el.classList.contains('toc') || tag === 'CANVAS' || tag === 'SCRIPT' || tag === 'STYLE') return;
        if (tag === 'H2') out += para('', 0, 0) + para(clean(el.innerText), 3, 0);
        else if (tag === 'H3') out += para(clean(el.innerText), 1, 0);
        else if (tag === 'TABLE') out += tableXml(el) + para('', 0, 0);
        else if (tag === 'UL' || tag === 'OL') {
          Array.prototype.slice.call(el.children).forEach(function (li) { out += para('· ' + clean(li.innerText), 0, 0); });
        } else if (el.classList.contains('kpis')) {
          Array.prototype.slice.call(el.children).forEach(function (k) {
            out += para('· ' + clean(k.querySelector('.kl').innerText) + ': ' + clean(k.querySelector('.kv').innerText) + ' (' + clean(k.querySelector('.ks').innerText) + ')', 0, 0);
          });
        } else if (el.classList.contains('fund')) {
          out += para(clean(el.querySelector('.fh').innerText), 1, 0);
          Array.prototype.slice.call(el.querySelectorAll('li')).forEach(function (li) { out += para('· ' + clean(li.innerText), 0, 0); });
        } else if (tag === 'P' || el.classList.contains('note')) out += para(clean(el.innerText), 6, 0);
        else if (el.classList.contains('need')) out += para(clean(el.innerText), 6, 0);
        else if (el.classList.contains('chart') || el.querySelector(':scope > canvas')) return;
        else if (tag === 'FOOTER') out += para(clean(el.innerText), 6, 2);
        else if (el.children.length) walk(el);
      });
    }
    Array.prototype.slice.call(root.querySelectorAll(':scope > section, :scope > footer')).forEach(function (s) {
      if (s.tagName === 'FOOTER') { out += para('', 0, 0) + para(clean(s.innerText), 6, 2); } else walk(s);
    });
    return out;
  }

  function sectionXml() {
    var first = '<hp:p id="1" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><hp:run charPrIDRef="0">' +
      '<hp:secPr id="" textDirection="HORIZONTAL" spaceColumns="1134" tabStop="8000" tabStopVal="4000" tabStopUnit="HWPUNIT" outlineShapeIDRef="0" memoShapeIDRef="0" textVerticalWidthHead="0" masterPageCnt="0">' +
      '<hp:grid lineGrid="0" charGrid="0" wonggojiFormat="0"/><hp:startNum pageStartsOn="BOTH" page="0" pic="0" tbl="0" equation="0"/>' +
      '<hp:visibility hideFirstHeader="0" hideFirstFooter="0" hideFirstMasterPage="0" border="SHOW_ALL" fill="SHOW_ALL" hideFirstPageNum="0" hideFirstEmptyLine="0" showLineNumber="0"/>' +
      '<hp:lineNumberShape restartType="0" countBy="0" distance="0" startNumber="0"/>' +
      '<hp:pagePr landscape="WIDELY" width="59528" height="84186" gutterType="LEFT_ONLY"><hp:margin header="4252" footer="4252" gutter="0" left="8504" right="8504" top="5668" bottom="4252"/></hp:pagePr>' +
      '</hp:secPr><hp:ctrl><hp:colPr id="" type="NEWSPAPER" layout="LEFT" colCount="1" sameSz="1" sameGap="0"/></hp:ctrl><hp:t></hp:t></hp:run></hp:p>';
    return XML + '<hs:sec ' + NS + '>' + first + bodyXml() + '</hs:sec>';
  }

  window.exportHwp = function () {
    if (!window.JSZip) { alert('내보내기 라이브러리를 불러오지 못했습니다. 인터넷 연결을 확인해 주세요.'); return; }
    pid = 1000;
    var zip = new JSZip();
    var NF = null;
    var addFile = zip.file.bind(zip);
    zip.file = function (n, d, o) { return addFile(n, d, Object.assign({ createFolders: false }, o || {})); };
    zip.file('mimetype', 'application/hwp+zip', { compression: 'STORE' });
    zip.file('version.xml', XML + '<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" tagetApplication="WORDPROCESSOR" major="5" minor="0" micro="5" buildNumber="0" os="1" xmlVersion="1.2" application="Hancom Office Hangul" appVersion="11, 0, 0, 0 WIN32LEWindows_Unknown_Version"/>');
    zip.file('META-INF/container.xml', XML + '<ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container" xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf"><ocf:rootfiles><ocf:rootfile full-path="Contents/content.hpf" media-type="application/hwpml-package+xml"/></ocf:rootfiles></ocf:container>');
    zip.file('META-INF/manifest.xml', XML + '<odf:manifest xmlns:odf="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"/>');
    zip.file('Contents/content.hpf', XML + '<opf:package ' + NS + ' version="" unique-identifier="" id=""><opf:metadata><opf:title>' + esc(FNAME) + '</opf:title><opf:language>ko</opf:language></opf:metadata>' +
      '<opf:manifest><opf:item id="header" href="Contents/header.xml" media-type="application/xml"/><opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/></opf:manifest>' +
      '<opf:spine><opf:itemref idref="header" linear="yes"/><opf:itemref idref="section0" linear="yes"/></opf:spine></opf:package>');
    zip.file('Contents/header.xml', headerXml());
    zip.file('Contents/section0.xml', sectionXml());
    zip.generateAsync({ type: 'blob', mimeType: 'application/hwp+zip', compression: 'DEFLATE' }).then(function (blob) {
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = FNAME + '.hwpx';
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 1500);
    });
  };
})();
