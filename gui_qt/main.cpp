#include <QApplication>
#include <QFont>

#include "main_window.h"

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    app.setApplicationName("Multi-Agent Chat");
    app.setOrganizationName("Multi-Agent Project");

    QFont font("Segoe UI", 10);
    app.setFont(font);

    app.setStyleSheet(R"(
        QToolTip {
            color: #f2f2f4;
            background: #19191f;
            border: 1px solid #4a2024;
            padding: 6px;
        }
        QScrollBar:vertical {
            width: 10px;
            margin: 2px;
            background: transparent;
        }
        QScrollBar::handle:vertical {
            min-height: 30px;
            border-radius: 5px;
            background: #34343d;
        }
        QScrollBar::handle:vertical:hover {
            background: #7d252d;
        }
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0;
        }
    )");

    MainWindow window;
    window.resize(1360, 860);
    window.show();

    return app.exec();
}
