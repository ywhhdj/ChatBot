<script setup lang="ts">

const characterList = ref([
  {
    id: 1,
    name: '小王',
    desc: '小王是游戏里的一个角色，他很懒，什么都没干。',
    avatar: 'https://picsum.photos/200/300'
  }
]);
function isSelected(id: number): boolean {
  return true;
  // return gameStore.avatar.character_id === id;
}
const selectRole = async (characterId: number): Promise<void> => {
  try {
    // await characterSelect({
    //   user_id: userId.value.toString(),
    //   character_id: characterId.toString(),
    // });
    // updateSelectedStatus();
  } catch (error) {
    console.error('切换角色失败:', error);
  }
};
</script>

<template>

  <MenuItem
    title="角色列表"
    button-text="刷新"
    @click=""
  >
  <RoleList>
    <RoleCard
      v-for="(character, index) in characterList"
      :key="index"
      :avatar="character.avatar"
      :name="character.name"
      :desc="character.desc"
    >
      <template #actions>
        <Button
          type="select"
          :class="['character-select-btn', { selected: isSelected(character.id) }]"
          @click="selectRole(character.id)"
        >{{ isSelected(character.id) ? '√ 选中' : '选择' }}</Button>
      </template>
    </RoleCard>
  </RoleList>
  </MenuItem>
</template>

<style scoped>
.character-select-btn {
  position: absolute;
  bottom: 15px;
  right: 15px;
  background-color: #5e72e4;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 20px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
  font-weight: 500;
}

.character-select-btn:hover {
  background-color: #4a5acf;
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(94, 114, 228, 0.3);
}

.selected {
  background-color: #10b981 !important;
}
</style>