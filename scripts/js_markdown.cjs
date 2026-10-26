// scan-to-md.js
const fs = require('fs');
const path = require('path');
const project_root = __dirname + "/..";

const config = {
  inputDir: project_root,
  outputFile: project_root + "/docs/vue-project.md",    // 输出的 markdown 文件名
  ignoreDirs: [
    'node_modules',
    '.git',
    'dist',
    '.cache',
    '__pycache__',
    "src_py",
    "resources",
    "static",
    "typings",
    "router",
    "assets",
    "utils",
    "docs",
    ".vscode",
    "scripts",
    "tests",
    ".vscode"
  ],
  ignoreFiles: [
    '.DS_Store',
    'package-lock.json',
    'yarn.lock',
    'scan-to-md.js',
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "auto-imports.d.ts",
    "components.d.ts",
    "package.json"
  ],
  includeExtensions: ['.vue', '.ts', '.css', ".gitignore"],
  split: {
    enabled: true,
    maxCharsPerFile: 80000,     // 每个文件最大字符数（保守留余量，AI 上下文一般 100k~200k tokens）
    indexFileName: 'README.md', // 索引文件名（放在输出目录）
  },
};

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

// 读取单个文件的内容块（不含文件树）
function readFileBlock(relPath) {
  const absPath = path.join(config.inputDir, relPath);
  const ext = path.extname(relPath).slice(1);
  try {
    const content = fs.readFileSync(absPath, 'utf-8');
    return `## \`${relPath}\`\n\n\`\`\`${ext}\n${content}\n\`\`\`\n\n`;
  } catch (err) {
    return `## \`${relPath}\`\n\n> ⚠️ 无法读取文件: ${err.message}\n\n`;
  }
}

// 生成文件树 markdown
function generateFileTreeMarkdown(treeLines) {
  return '# 项目文件树\n\n```\n' + treeLines.join('\n') + '\n```\n';
}

// 主函数（单文件模式）
function mainSingleFile() {
  console.log('🔍 正在扫描项目...');
  const { fileList, treeLines } = walkDir(config.inputDir);
  console.log(`📁 找到 ${fileList.length} 个代码文件`);

  let md = '# Vue 项目结构与代码\n\n';
  md += '## 文件树\n\n```\n' + treeLines.join('\n') + '\n```\n\n---\n\n';

  for (const relPath of fileList) {
    md += readFileBlock(relPath);
  }

  fs.writeFileSync(config.outputFile, md, 'utf-8');
  console.log(`✅ 已生成 ${config.outputFile} (${(md.length / 1024).toFixed(1)} KB)`);
}

// 主函数（多文件分割模式）
function mainSplitFiles() {
  console.log('🔍 正在扫描项目...');
  const { fileList, treeLines } = walkDir(config.inputDir);
  console.log(`📁 找到 ${fileList.length} 个代码文件`);

  // 确定输出目录
  const baseOutput = config.outputFile.replace(/\.md$/, '');
  const outputDir = baseOutput + '_parts';
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  const maxChars = config.split.maxCharsPerFile;

  // === 第 0 部分：文件树 ===
  let partIndex = 0;
  partIndex++;

  // === 后续部分：按文件逐个填入，超过上限就切到下一份 ===
  let currentContent = '';
  let currentFileCount = 0;
  let partFileList = []; // 记录每个 part 包含的文件

  const allParts = []; // 记录所有 part 的信息

  for (let i = 0; i < fileList.length; i++) {
    const relPath = fileList[i];
    const block = readFileBlock(relPath);

    // 如果当前内容 + 新文件块超过上限，且已有内容不为空，则先写入当前部分
    if (currentContent.length > 0 && (currentContent.length + block.length) > maxChars) {
      const partFileName = `part${String(partIndex).padStart(2, '0')}_代码文件.md`;
      const partPath = path.join(outputDir, partFileName);
      const header = `# 项目代码文件（第 ${partIndex} 部分）\n\n> 本文件包含 ${currentFileCount} 个文件\n\n---\n\n`;
      const fullContent = header + currentContent;
      fs.writeFileSync(partPath, fullContent, 'utf-8');
      console.log(`  📝 写入 ${path.relative(__dirname, partPath)} (${(fullContent.length / 1024).toFixed(1)} KB, ${currentFileCount} 个文件)`);
      allParts.push({ path: partPath, fileCount: currentFileCount, files: [...partFileList] });

      // 重置
      currentContent = '';
      currentFileCount = 0;
      partFileList = [];
      partIndex++;
    }

    currentContent += block;
    currentFileCount++;
    partFileList.push(relPath);
  }

  // 写入最后剩余的部分
  if (currentContent.length > 0) {
    const partFileName = `part${String(partIndex).padStart(2, '0')}_代码文件.md`;
    const partPath = path.join(outputDir, partFileName);
    const header = `# 项目代码文件（第 ${partIndex} 部分）\n\n> 本文件包含 ${currentFileCount} 个文件\n\n---\n\n`;
    const fullContent = header + currentContent;
    fs.writeFileSync(partPath, fullContent, 'utf-8');
    console.log(`  📝 写入 ${path.relative(__dirname, partPath)} (${(fullContent.length / 1024).toFixed(1)} KB, ${currentFileCount} 个文件)`);
    allParts.push({ path: partPath, fileCount: currentFileCount, files: [...partFileList] });
  }

  // === 生成索引文件（README.md）===
  let readme = '# 项目结构与代码 - 索引\n\n';
  readme += `> 共分割为 ${partIndex + 1} 个文件（含文件树），每文件上限 ${maxChars} 字符\n\n`;
  readme += `## 📑 文件列表\n\n`;
  readme += `| 序号 | 文件名 | 包含文件 | 大小 |\n`;
  readme += `|------|--------|----------|------|\n`;

  // 各代码部分
  allParts.forEach((part, idx) => {
    const stat = fs.statSync(part.path);
    const fileName = path.basename(part.path);
    const fileNames = part.files.map(f => `\`${f}\``).join(', ');
    readme += `| ${idx + 1} | [${fileName}](./${fileName}) | ${fileNames} | ${(stat.size / 1024).toFixed(1)} KB |\n`;
  });

  readme += `\n## 📁 完整文件树\n\n`;
  readme += '```\n' + treeLines.join('\n') + '\n```\n';

  const indexPath = path.join(outputDir, config.split.indexFileName);
  fs.writeFileSync(indexPath, readme, 'utf-8');
  console.log(`\n✅ 已生成索引文件 ${path.relative(__dirname, indexPath)}`);
  console.log(`📊 总计: ${partIndex} 个文件，输出目录: ${path.relative(__dirname, outputDir)}`);
}

// 主入口
function main() {
  if (config.split.enabled) {
    mainSplitFiles();
  } else {
    mainSingleFile();
  }
}

main();