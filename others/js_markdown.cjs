// scan-to-md.js
const fs = require('fs');
const path = require('path');

// 配置项
const config = {
  inputDir: __dirname + "/../src/",          // 扫描当前目录
  outputFile: __dirname + "/docs/vue-project.md",    // 输出的 markdown 文件名
  ignoreDirs: ['node_modules', '.git', 'dist', '.cache', '__pycache__', "src_py", "resources", "static","typings","router","assets","utils"], // 忽略的目录
  ignoreFiles: ['.DS_Store', 'package-lock.json', 'yarn.lock', 'scan-to-md.js', "pnpm-lock.yaml","auto-imports.d.ts","components.d.ts"], // 忽略的文件
  includeExtensions: ['.vue','.ts','.css'], // 只包含这些扩展名的文件（可自定义）
};

// 递归获取文件列表
function walkDir(dir, fileList = [], prefix = '') {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  let treeLines = [];

  entries.sort((a, b) => a.name.localeCompare(b.name));

  for (let i = 0; i < entries.length; i++) {
    const entry = entries[i];
    const fullPath = path.join(dir, entry.name);
    const relativePath = path.relative(config.inputDir, fullPath).replace(/\\/g, '/');

    // 跳过忽略目录
    if (entry.isDirectory()) {
      if (config.ignoreDirs.includes(entry.name)) continue;
      const subTree = walkDir(fullPath, fileList, `${prefix}${entry.name}/`);
      treeLines.push(`${prefix}📁 ${entry.name}/`);
      treeLines = treeLines.concat(subTree.treeLines.map(l => `  ${l}`));
    } else {
      // 跳过忽略文件
      if (config.ignoreFiles.includes(entry.name)) continue;
      // 按扩展名过滤
      const ext = path.extname(entry.name).toLowerCase();
      if (!config.includeExtensions.includes(ext)) continue;

      treeLines.push(`${prefix}📄 ${entry.name}`);
      fileList.push(relativePath);
    }
  }
  return { fileList, treeLines };
}

// 生成 Markdown
function generateMarkdown(fileList, treeLines) {
  let md = '# Vue 项目结构与代码\n\n';
  md += '## 文件树\n\n```\n' + treeLines.join('\n') + '\n```\n\n---\n\n';

  for (const relPath of fileList) {
    const absPath = path.join(config.inputDir, relPath);
    try {
      const content = fs.readFileSync(absPath, 'utf-8');
      const ext = path.extname(relPath).slice(1);
      md += `## \`${relPath}\`\n\n\`\`\`${ext}\n${content}\n\`\`\`\n\n`;
    } catch (err) {
      md += `## \`${relPath}\`\n\n> ⚠️ 无法读取文件: ${err.message}\n\n`;
    }
  }
  return md;
}

// 主函数
function main() {
  console.log('🔍 正在扫描项目...');
  const { fileList, treeLines } = walkDir(config.inputDir);
  console.log(`📁 找到 ${fileList.length} 个代码文件`);

  const mdContent = generateMarkdown(fileList, treeLines);
  fs.writeFileSync(config.outputFile, mdContent, 'utf-8');
  console.log(`✅ 已生成 ${config.outputFile}`);
}

main();