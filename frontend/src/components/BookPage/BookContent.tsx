import { Component } from "solid-js";

interface BookContentProps {
    content: string;
    coverImage: string;
    showCover: boolean;
}

const BookContent: Component<BookContentProps> = (props) => {
    return (
        <div class="flex flex-col items-center">
            {props.showCover ? (
                <img
                    src={props.coverImage}
                    alt="Book cover"
                    class="w-full max-w-md h-72 sm:h-96 md:h-[28rem] lg:h-[32rem] object-cover rounded-lg shadow-lg mb-8"
                />
            ) : (
                <p class="prose max-w-none text-xl font-rounded leading-relaxed">
                    {props.content}
                </p>
            )}
        </div>
    );
}

export default BookContent;