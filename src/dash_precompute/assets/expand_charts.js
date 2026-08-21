(() => {
  let expandedCard = null;
  const expandedPlots = new WeakMap();

  const cloneValue = (value) => {
    if (value === undefined || value === null) return value;
    return JSON.parse(JSON.stringify(value));
  };

  const getPath = (object, path) =>
    path.split(".").reduce((value, key) => value?.[key], object);

  const scaleValue = (value, factor, minimum = 0) => {
    if (Array.isArray(value)) {
      return value.map((item) => scaleValue(item, factor, minimum));
    }
    if (typeof value !== "number") return value;
    return Math.max(minimum, Math.round(value * factor * 10) / 10);
  };

  const expandedScale = (card) => {
    const { width, height } = card.getBoundingClientRect();
    if (width < 900 || height < 600) return 1.35;
    if (width < 1500 || height < 850) return 1.5;
    return 1.7;
  };

  const resizePlot = (card) =>
    new Promise((resolve) => {
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(async () => {
          const plot = card.querySelector(".js-plotly-plot");
          if (window.Plotly && plot) {
            await window.Plotly.Plots.resize(plot);
          } else {
            window.dispatchEvent(new Event("resize"));
          }
          resolve(plot);
        });
      });
    });

  const scaleSubtitle = (text, factor) => {
    if (typeof text !== "string") return text;
    return text.replace(/font-size:(\d+(?:\.\d+)?)px/g, (_match, size) => {
      return `font-size:${Math.round(Number(size) * factor)}px`;
    });
  };

  const buildExpandedLayout = (plot, factor, state) => {
    const inputLayout = plot.layout || {};
    const fullLayout = plot._fullLayout || {};
    const update = {};
    const paths = [
      ["font.size", 13],
      ["title.font.size", 20],
      ["legend.font.size", 12],
      ["hoverlabel.font.size", 13],
      ["xaxis.tickfont.size", 12],
      ["xaxis.title.font.size", 13],
      ["yaxis.tickfont.size", 12],
      ["yaxis.title.font.size", 13],
      ["coloraxis.colorbar.tickfont.size", 12],
      ["coloraxis.colorbar.title.font.size", 13],
    ];

    for (const [path, minimum] of paths) {
      const inputValue = getPath(inputLayout, path);
      const fullValue = getPath(fullLayout, path);
      const value = inputValue ?? fullValue;
      if (typeof value !== "number") continue;
      state.layout[path] = cloneValue(inputValue);
      update[path] = scaleValue(value, factor, minimum);
    }

    if (inputLayout.title?.text) {
      state.layout["title.text"] = inputLayout.title.text;
      update["title.text"] = scaleSubtitle(inputLayout.title.text, factor);
    }

    const margin = cloneValue(inputLayout.margin || fullLayout.margin);
    if (margin) {
      state.layout.margin = cloneValue(inputLayout.margin);
      update.margin = {
        ...margin,
        l: scaleValue(margin.l || 0, Math.min(factor, 1.5), 36),
        r: scaleValue(margin.r || 0, Math.min(factor, 1.5), 28),
        t: scaleValue(margin.t || 0, Math.min(factor, 1.45), 86),
        b: scaleValue(margin.b || 0, Math.min(factor, 1.45), 56),
      };
    }

    const annotations = cloneValue(inputLayout.annotations);
    if (annotations?.length) {
      state.layout.annotations = cloneValue(inputLayout.annotations);
      update.annotations = annotations.map((annotation) => ({
        ...annotation,
        font: {
          ...(annotation.font || {}),
          size: scaleValue(
            annotation.font?.size ?? fullLayout.font?.size ?? 11,
            factor,
            13,
          ),
        },
        xshift: scaleValue(annotation.xshift || 0, factor),
        yshift: scaleValue(annotation.yshift || 0, factor),
      }));
    }

    if (inputLayout.meta?.expanded_showlegend) {
      state.layout.showlegend = inputLayout.showlegend;
      update.showlegend = true;
    }

    return update;
  };

  const traceStylePaths = [
    ["line.width", 2],
    ["marker.size", 7],
    ["marker.line.width", 1.5],
    ["textfont.size", 13],
    ["insidetextfont.size", 13],
    ["outsidetextfont.size", 13],
    ["marker.colorbar.tickfont.size", 12],
    ["marker.colorbar.title.font.size", 13],
  ];

  const applyExpandedTraceStyles = async (plot, factor, state) => {
    for (let index = 0; index < plot.data.length; index += 1) {
      const trace = plot.data[index];
      const fullTrace = plot._fullData?.[index] || {};
      const traceState = {};
      const update = {};
      for (const [path, minimum] of traceStylePaths) {
        const inputValue = getPath(trace, path);
        const fullValue = getPath(fullTrace, path);
        const value = inputValue ?? fullValue;
        if (typeof value !== "number" && !Array.isArray(value)) continue;
        traceState[path] = cloneValue(inputValue);
        update[path] = [scaleValue(value, factor, minimum)];
      }
      if (Object.keys(update).length) {
        state.traces[index] = traceState;
        await window.Plotly.restyle(plot, update, [index]);
      }
    }
  };

  const applyExpandedPresentation = async (card, plot) => {
    if (!window.Plotly || !plot) return;
    const factor = expandedScale(card);
    const state = { layout: {}, traces: {} };
    expandedPlots.set(plot, state);
    const layoutUpdate = buildExpandedLayout(plot, factor, state);
    await window.Plotly.relayout(plot, layoutUpdate);
    await applyExpandedTraceStyles(plot, factor, state);
    await window.Plotly.Plots.resize(plot);
  };

  const restoreOverviewPresentation = async (plot) => {
    if (!window.Plotly || !plot) return;
    const state = expandedPlots.get(plot);
    if (!state) return;

    for (const [indexText, properties] of Object.entries(state.traces)) {
      const update = {};
      for (const [path, value] of Object.entries(properties)) {
        update[path] = [value ?? null];
      }
      await window.Plotly.restyle(plot, update, [Number(indexText)]);
    }

    const layoutUpdate = {};
    for (const [path, value] of Object.entries(state.layout)) {
      layoutUpdate[path] = value ?? null;
    }
    await window.Plotly.relayout(plot, layoutUpdate);
    expandedPlots.delete(plot);
  };

  const closeExpandedCard = async () => {
    if (!expandedCard) return;

    const card = expandedCard;
    const button = card.querySelector(".expand-button");
    const plot = card.querySelector(".js-plotly-plot");
    await restoreOverviewPresentation(plot);
    card.classList.remove("is-expanded");
    document.body.classList.remove("chart-expanded");
    if (button) {
      button.textContent = "⤢";
      button.title = button.dataset.expandTitle;
      button.setAttribute("aria-label", button.dataset.expandTitle);
      button.setAttribute("aria-expanded", "false");
    }
    expandedCard = null;
    await resizePlot(card);
  };

  document.addEventListener("click", async (event) => {
    const button = event.target.closest(".expand-button");
    if (!button) return;

    const card = button.closest(".expandable-card");
    if (!card) return;

    if (card === expandedCard) {
      await closeExpandedCard();
      return;
    }

    await closeExpandedCard();
    button.dataset.expandTitle ||= button.title;
    card.classList.add("is-expanded");
    document.body.classList.add("chart-expanded");
    button.textContent = "×";
    button.title = "Close expanded chart";
    button.setAttribute("aria-label", "Close expanded chart");
    button.setAttribute("aria-expanded", "true");
    expandedCard = card;
    const plot = await resizePlot(card);
    await applyExpandedPresentation(card, plot);
  });

  document.addEventListener("keydown", async (event) => {
    if (event.key === "Escape") await closeExpandedCard();
  });
})();
