import { Component, For } from "solid-js";

interface Category {
  id: string;
  name: string;
  icon: string;
  color: string;
}

const categories: Category[] = [
  { id: 'adventure', name: 'Adventure', icon: '🗺️', color: 'bg-yellow-400' },
  { id: 'fantasy', name: 'Fantasy', icon: '🐉', color: 'bg-purple-400' },
  { id: 'animals', name: 'Animals', icon: '🦁', color: 'bg-green-400' },
  { id: 'bedtime', name: 'Bedtime', icon: '🌙', color: 'bg-blue-400' },
];

interface Props {
  selected: string;
  onSelect: (category: string) => void;
}

const CategoryFilter: Component<Props> = (props) => {
  return (
    <div class="flex gap-4 justify-center mb-8 flex-wrap">
      <For each={categories}>
        {(category) => (
          <button
            onClick={() => props.onSelect(category.id)}
            class={`${category.color} transform hover:scale-110 transition-transform
              rounded-full py-2 px-6 flex items-center gap-2 shadow-lg
              ${props.selected === category.id ? 'ring-4 ring-kiddy-primary' : ''}
            `}
          >
            <span class="text-2xl">{category.icon}</span>
            <span class="font-comic text-lg">{category.name}</span>
          </button>
        )}
      </For>
    </div>
  );
}

export default CategoryFilter;