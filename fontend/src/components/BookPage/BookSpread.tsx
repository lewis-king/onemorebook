import { Component, onMount, onCleanup, For } from "solid-js";
import { PageFlip } from 'page-flip';
import { TbStarFilled } from "solid-icons/tb";
import "./PageFlip.css";

interface BookSpreadProps {
  pages: string[];
  coverImage?: string;
  onPageFlipInit: (pageFlip: any) => void;
  onPageChange: (pageNumber: number) => void;
  bookId: string;
  stars: number;
  onUpvote: (id: string, currentStars: number) => void;
  pageImages?: { url: string }[];
}

export const BookSpread: Component<BookSpreadProps> = (props) => {
  let bookElement: HTMLDivElement | undefined;
  let pageFlip: PageFlip | undefined;

  onMount(() => {
    if (bookElement) {
      pageFlip = new PageFlip(bookElement, {
        width: 550,
        height: 733,
        size: "stretch",
        minWidth: 315,
        maxWidth: 1000,
        minHeight: 420,
        maxHeight: 1350,
        maxShadowOpacity: 0.5,
        showCover: true,
        mobileScrollSupport: false,
        usePortrait: true,
        flippingTime: 1000,
        drawShadow: true,
        startZIndex: 0
      });

      // Initialize pages
      pageFlip.loadFromHTML(document.querySelectorAll(".page"));

      // Show book after initialization
      if (bookElement) {
        bookElement.style.display = 'block';
      }

      props.onPageFlipInit(pageFlip);

      pageFlip.on('flip', (e) => {
        props.onPageChange(e.data);
      });

      const handleResize = () => {
        if (pageFlip) {
          pageFlip.updateFromState();
        }
      };

      window.addEventListener('resize', handleResize);
      window.addEventListener('orientationchange', handleResize);

      onCleanup(() => {
        window.removeEventListener('resize', handleResize);
        window.removeEventListener('orientationchange', handleResize);
      });
    }
  });

  onCleanup(() => {
    pageFlip?.destroy();
  });

  const getPageImage = (index: number) => {
    // Adjust index to account for cover page
    const imageIndex = index - 1;
    if (imageIndex < 0 || !props.pageImages || imageIndex >= props.pageImages.length) {
      return undefined;
    }
    return props.pageImages[imageIndex].url;
  };

  return (
      <div class="book-container">
        <div ref={bookElement} class="book">
          <For each={props.pages}>
            {(content, index) => {
              const isFirstPage = index() === 0;
              const isLastPage = index() === props.pages.length - 1;
              const pageImage = getPageImage(index());

              return (
                  <div class={`page ${isFirstPage ? 'page-cover page-cover-top' : ''} 
                          ${isLastPage ? 'page-cover page-cover-bottom' : ''}`}>
                    <div class="page-content">
                      {isLastPage ? (
                          <div class="flex flex-col justify-center items-center h-full">
                            <button
                                onClick={() => props.onUpvote(props.bookId, props.stars)}
                                class="group bg-kiddy-primary hover:bg-kiddy-secondary
                               transition-all duration-300 rounded-2xl p-8
                               shadow-xl hover:shadow-2xl transform
                               hover:scale-105 cursor-pointer"
                            >
                              <div class="text-4xl font-comic text-white mb-4">
                                Did you love this story? 📚
                              </div>
                              <div class="flex items-center justify-center gap-3">
                                <TbStarFilled class="text-yellow-400 w-12 h-12" />
                                <span class="text-3xl font-comic text-white">
                            {props.stars}
                          </span>
                              </div>
                            </button>
                          </div>
                      ) : isFirstPage ? (
                          <div class="h-full w-full">
                            <img
                                src={props.coverImage}
                                alt="Story cover"
                                class="h-full w-full object-cover"
                            />
                          </div>
                      ) : (
                          <div class="flex flex-col h-full">
                            {pageImage ? (
                                <>
                                  <div class="page-image">
                                    <img
                                        src={pageImage}
                                        alt={`Story illustration for page ${index()}`}
                                        class="w-full h-full object-contain"
                                    />
                                  </div>
                                  <div class="page-text flex-grow">
                                    {content}
                                  </div>
                                </>
                            ) : (
                                <div class="page-text centered">
                                  {content}
                                </div>
                            )}
                            <div class="page-footer mt-auto">
                              Page {index()}
                            </div>
                          </div>
                      )}
                    </div>
                  </div>
              );
            }}
          </For>
        </div>
      </div>
  );
}