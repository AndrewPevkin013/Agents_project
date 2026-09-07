#include <QApplication>
#include <QFont>
#include <QPointer>

#include "auth_client.h"
#include "login_dialog.h"
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

    AuthClient authClient;

    while (true) {
        LoginDialog loginDialog(&authClient);

        if (loginDialog.exec() != QDialog::Accepted) {
            return 0;
        }

        MainWindow window(
            authClient.username(),
            authClient.accessToken());

        window.resize(1360, 860);

        bool logoutRequested = false;

        QObject::connect(
            &window,
            &MainWindow::logoutRequested,
            &app,
            [&]() {
                logoutRequested = true;
                authClient.logout();
            });

        QObject::connect(
            &authClient,
            &AuthClient::logoutSucceeded,
            &window,
            [&window]() {
                window.close();
            });

        window.show();
        app.exec();

        if (!logoutRequested) {
            break;
        }
    }

    return 0;
}
