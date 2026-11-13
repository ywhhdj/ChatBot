<script setup lang="ts">
const markdownContent = String.raw`
# 记忆系统设计（SQLite + FAISS）

## 普通文本与行内代码

行内代码：\`marked.lexer(md)\`、\`faiss_id -> memory_id\`，还有带反引号的：\`\`a\\\`b\`\`。

模板变量插值需要转义：\${notARealVar}

## 公式

$$
f(x) = \int_{-\infty}^\infty
E = mc^2
$$



## JSON 代码块

\`\`\`json
{
  "id": 1,
  "session_id": "s-001",
  "role": "user",
  "content": "hello",
  "importance": 0.82,
  "metadata": { "source": "chat", "tags": ["a", "b"] }
}
\`\`\`

## TypeScript 代码块

\`\`\`ts
type Memory = {
  id: number
  content: string
  importance: number
}

const top = memories.sort((a, b) => b.importance - a.importance).slice(0, 100)
\`\`\`

## 无语言标记（走 plaintext 兜底）

\`\`\`
plain text, no highlight
<tag> & "quotes" 会被怎么处理
\`\`\`

## 表格 / 列表

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| id | INTEGER | 记忆 ID |
| content | TEXT | 内容 |

- 列表项 \`code\`
- 列表项 **加粗**
`
</script>

<template>
  <div class="toolbar_workspaceTitleRow__W77m9">
    <div class="toolbar_leftConfig__2VEXd">
      <div class="toolbar_title__L3GYg">对话调用链修复清单.md</div>
    </div>
    <div class="toolbar_rightConfig__iciBo">
      <div>
        <div>
          <div class="toolbar_icon__ULsTV"><span
              class="yb-icon iconfont-yb iconfont-canvas icon-yb-ic_copy_2504 toolbar_ybIconIc__xaOVj"
              style="line-height: 1;"
            ></span></div>
        </div>
      </div>
      <div>
        <div class="yb-canvas-toolbar-download download_container__Urzy5">
          <div
            class="download_downloadBtn__EGuDL"
            role="button"
            aria-label="下载到本地"
          ><span
              class="yb-icon iconfont-yb iconfont-canvas icon-yb-ic_download_large_16 download_ybIconIc__FWaUf"
              style="line-height: 1;"
            ></span></div>
        </div>
      </div>
      <div>
        <div>
          <div
            class="t-radio-group t-size-s tabs-btn_tabsBtnContainer__GboSg t-radio-group--filled">
            <label
              tabindex="0"
              class="t-radio-button"
            ><input
                type="radio"
                class="t-radio-button__former"
                tabindex="-1"
                data-value="'code'"
                value="code"
              ><span class="t-radio-button__input"></span><span class="t-radio-button__label"><span
                  class="t-trigger"
                >代码</span></span></label><label
              tabindex="0"
              class="t-radio-button t-is-checked"
            ><input
                type="radio"
                class="t-radio-button__former"
                tabindex="-1"
                data-value="'preview'"
                value="preview"
              ><span class="t-radio-button__input"></span><span class="t-radio-button__label"><span
                  class="t-trigger"
                >预览</span></span></label>
            <div
              class="t-radio-group__bg-block"
              style="width: 52px; height: 24px; left: 54px; top: 2px;"
            ></div>
          </div>
        </div>
      </div>
    </div>
  </div>
  <div class="markdown-view">
    <Markdown
      class="markdown-scroller"
      :content="markdownContent"
    />
  </div>
</template>
<style scoped>
.markdown-view {
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.markdown-scroller {
  flex: 1;
  min-height: 0;
  width: 85%;
}
</style>
