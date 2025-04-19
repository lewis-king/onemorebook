import { Component } from "solid-js";

interface PageProps {
  content: string;
  imageUrl: string;
}

export const Page: Component<PageProps> = (props) => {
  return (
    <div class="h-full flex flex-col">
      <img 
        src={props.imageUrl} 
        alt="Story illustration"
        class="w-full h-48 object-cover rounded-lg mb-4"
      />
      <p class="text-lg font-comic text-center py-4 flex-grow">
        {props.content}
      </p>
    </div>
  );
};